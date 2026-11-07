"""M4: CCNA-level fault campaign.

For each fault: check the network is healthy, inject the fault, wait for the
network to react, run the validator in full mode and in ping-only mode,
repair the fault, wait until the network is healthy again, and record the
result. At the end, write the fault ledger (results/fault-ledger.md).

Run from the repo root:
    python3 faults/campaign.py                  # all 8 faults (about 20 minutes)
    python3 faults/campaign.py --only ospf-area # one fault
    python3 faults/campaign.py --list           # show the faults
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VALIDATOR = REPO / "validator" / "validate.py"
FAULT_DIR = REPO / "results" / "faults"
LEDGER = REPO / "results" / "fault-ledger.md"
LAB_PREFIX = "clab-netops-"
SETTLE_SECONDS = 50  # longer than the OSPF dead interval (40 s), so every fault has fully taken effect


# ---------------------------------------------------------------- lab helpers

def sh(node, *args):
    """Run a command inside a lab container and return its output."""
    out = subprocess.run(["docker", "exec", LAB_PREFIX + node, *args],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"{node}: '{' '.join(args)}' failed: {out.stderr.strip()}")
    return out.stdout.strip()


def frr_config(node, *lines):
    """Apply FRR configuration lines, as if typed after 'configure terminal'."""
    args = ["vtysh", "-c", "configure terminal"]
    for line in lines:
        args += ["-c", line]
    sh(node, *args)


# ---------------------------------------------------------------- the faults
# Each fault has an inject() and a repair() action.

saved = {}  # values remembered between inject and repair (e.g. the original MTU)


def inject_mtu():
    saved["mtu"] = sh("wan-p1", "cat", "/sys/class/net/eth1/mtu")
    sh("wan-p1", "ip", "link", "set", "eth1", "mtu", "1400")
    sh("wan-p1", "vtysh", "-c", "clear ip ospf process")  # force the adjacency to form again


def repair_mtu():
    sh("wan-p1", "ip", "link", "set", "eth1", "mtu", saved["mtu"])
    sh("wan-p1", "vtysh", "-c", "clear ip ospf process")


FAULTS = [
    {
        "name": "link-down",
        "topic": "Interface status, redundancy",
        "description": "WAN link L2 shut down (wan-p1 eth2, towards a-edge)",
        "inject": lambda: sh("wan-p1", "ip", "link", "set", "eth2", "down"),
        "repair": lambda: sh("wan-p1", "ip", "link", "set", "eth2", "up"),
    },
    {
        "name": "ospf-passive",
        "topic": "OSPF passive interfaces",
        "description": "passive-interface on the provider core link (wan-p1 eth1)",
        "inject": lambda: frr_config("wan-p1", "router ospf", "passive-interface eth1"),
        "repair": lambda: frr_config("wan-p1", "router ospf", "no passive-interface eth1"),
    },
    {
        "name": "ospf-mtu",
        "topic": "OSPF adjacency requirements (MTU)",
        "description": "MTU lowered to 1400 on wan-p1 eth1 (neighbour keeps its MTU)",
        "inject": inject_mtu,
        "repair": repair_mtu,
    },
    {
        "name": "ospf-timers",
        "topic": "OSPF adjacency requirements (hello/dead timers)",
        "description": "hello interval 5 s on a-edge eth3 (a-core keeps 10 s)",
        "inject": lambda: frr_config("a-edge", "interface eth3", "ip ospf hello-interval 5"),
        "repair": lambda: frr_config("a-edge", "interface eth3", "no ip ospf hello-interval"),
    },
    {
        "name": "ospf-area",
        "topic": "OSPF areas",
        "description": "b-core puts link L7 in area 1 (b-edge keeps area 0)",
        "inject": lambda: frr_config("b-core", "router ospf",
                                     "no network 10.2.1.0/30 area 0", "network 10.2.1.0/30 area 1"),
        "repair": lambda: frr_config("b-core", "router ospf",
                                     "no network 10.2.1.0/30 area 1", "network 10.2.1.0/30 area 0"),
    },
    {
        "name": "missing-lan",
        "topic": "OSPF configuration (network statement)",
        "description": "a-core no longer advertises LAN 10.1.20.0/24 (h-a2)",
        "inject": lambda: frr_config("a-core", "router ospf", "no network 10.1.20.0/24 area 0"),
        "repair": lambda: frr_config("a-core", "router ospf", "network 10.1.20.0/24 area 0"),
    },
    {
        "name": "missing-loopback",
        "topic": "OSPF configuration (loopbacks)",
        "description": "b-core no longer advertises its loopback 10.2.0.2/32",
        "inject": lambda: frr_config("b-core", "router ospf", "no network 10.2.0.2/32 area 0"),
        "repair": lambda: frr_config("b-core", "router ospf", "network 10.2.0.2/32 area 0"),
    },
    {
        "name": "host-gateway",
        "topic": "IP addressing (default gateway)",
        "description": "h-b2 sends traffic to a wrong gateway (10.2.20.99)",
        "inject": lambda: sh("h-b2", "ip", "route", "replace", "10.0.0.0/8", "via", "10.2.20.99", "dev", "eth1"),
        "repair": lambda: sh("h-b2", "ip", "route", "replace", "10.0.0.0/8", "via", "10.2.20.1", "dev", "eth1"),
    },
]


# ---------------------------------------------------------------- validator runs

def run_validator(mode, label, save=True):
    """Run validate.py; a non-zero exit code means the run detected a problem."""
    cmd = [sys.executable, str(VALIDATOR), "--mode", mode, "--label", label]
    if not save:
        cmd.append("--no-save")
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    match = re.search(r"(\d+)/(\d+) checks passed", out.stdout)
    if not match:
        raise RuntimeError(f"validator did not run properly:\n{out.stderr}")
    return {"detected": out.returncode != 0, "passed": int(match[1]), "total": int(match[2])}


def wait_until_healthy(timeout=240):
    """Run the full validator every 10 s until everything passes; return the seconds it took."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if not run_validator("full", "health-check", save=False)["detected"]:
            return round(time.monotonic() - start)
        time.sleep(10)
    raise RuntimeError("the network did not become healthy; check the lab before continuing")


# ---------------------------------------------------------------- campaign

def run_fault(number, fault):
    label = f"fault{number}-{fault['name']}"
    print(f"\n=== Fault {number}: {fault['name']} ({fault['description']})")

    print("  checking the network is healthy first...")
    wait_until_healthy()

    print("  injecting the fault...")
    fault["inject"]()
    try:
        print(f"  waiting {SETTLE_SECONDS} s for the network to react...")
        time.sleep(SETTLE_SECONDS)
        full = run_validator("full", label)
        ping = run_validator("ping", label)
    finally:
        print("  repairing...")
        fault["repair"]()

    recovery = wait_until_healthy()
    print(f"  validator: {full['passed']}/{full['total']} -> {'DETECTED' if full['detected'] else 'missed'}")
    print(f"  ping only: {ping['passed']}/{ping['total']} -> {'DETECTED' if ping['detected'] else 'missed'}")
    print(f"  healthy again after about {recovery} s")

    record = {
        "number": number,
        "name": fault["name"],
        "topic": fault["topic"],
        "description": fault["description"],
        "validator_detected": full["detected"],
        "validator_failed_checks": full["total"] - full["passed"],
        "validator_total_checks": full["total"],
        "ping_detected": ping["detected"],
        "ping_failed_checks": ping["total"] - ping["passed"],
        "recovery_s": recovery,
    }
    FAULT_DIR.mkdir(parents=True, exist_ok=True)
    (FAULT_DIR / f"{label}.json").write_text(json.dumps(record, indent=2))


def write_ledger():
    records = sorted((json.loads(p.read_text()) for p in FAULT_DIR.glob("*.json")),
                     key=lambda r: r["number"])
    yes_no = {True: "detected", False: "**missed**"}
    lines = [
        "# Fault ledger",
        "",
        "| # | Fault | CCNA topic | Ping only | Validator | Validator failed checks |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| {r['number']} | {r['description']} | {r['topic']} | {yes_no[r['ping_detected']]} "
            f"| {yes_no[r['validator_detected']]} | {r['validator_failed_checks']}/{r['validator_total_checks']} |"
        )
    total = len(records)
    validator = sum(r["validator_detected"] for r in records)
    ping = sum(r["ping_detected"] for r in records)
    lines += ["", f"**Faults detected: validator {validator}/{total}, ping only {ping}/{total}.**", ""]
    LEDGER.write_text("\n".join(lines))
    print(f"\nLedger written to {LEDGER.relative_to(REPO)}:")
    print(f"  validator {validator}/{total}, ping only {ping}/{total}")


def main():
    parser = argparse.ArgumentParser(description="Run the CCNA-level fault campaign.")
    parser.add_argument("--only", help="run a single fault by name")
    parser.add_argument("--list", action="store_true", help="list the faults and exit")
    args = parser.parse_args()

    if args.list:
        for number, fault in enumerate(FAULTS, start=1):
            print(f"{number}. {fault['name']:<17} {fault['description']}")
        return

    for number, fault in enumerate(FAULTS, start=1):
        if args.only and fault["name"] != args.only:
            continue
        run_fault(number, fault)
    write_ledger()


if __name__ == "__main__":
    main()