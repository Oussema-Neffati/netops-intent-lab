"""M3.3: compare the live network with the intent, print a report and save it.

Run from the repo root:
    python3 validator/validate.py                      # all checks
    python3 validator/validate.py --mode ping          # ping-only baseline
    python3 validator/validate.py --label bgp-shut     # name the run (used in M4)

Exit code: 0 if every check passes, 1 otherwise.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from checks import (check_bgp, check_loopbacks, check_ospf, check_reachability,
                    check_routes, check_vrrp, result)

REPO = Path(__file__).resolve().parent.parent
INTENT_FILE = REPO / "intent" / "network.yml"
RUNS_DIR = REPO / "results" / "runs"


def run_protocol_checks(routers, standards):
    results = []
    for name, router in routers.items():
        try:
            results += check_ospf(name, routers)
            results += check_bgp(name, router, standards)
            results += check_routes(name, router)
            results += check_vrrp(name, router)
        except RuntimeError as error:
            results.append(result(name, "Router answers", "answers", str(error)))
    return results


def print_report(results):
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['router']:<7} {r['check']}")
        if not r["passed"]:
            print(f"          expected: {r['expected']}")
            print(f"          actual:   {r['actual']}")
    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} checks passed")


def save_report(results, mode, label, duration):
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    failed = [r for r in results if not r["passed"]]
    report = {
        "timestamp": stamp,
        "label": label,
        "mode": mode,
        "duration_s": duration,
        "total": len(results),
        "passed": len(results) - len(failed),
        "fault_detected": bool(failed),
        "failed_checks": failed,
    }
    path = RUNS_DIR / f"{stamp}-{label}-{mode}.json"
    path.write_text(json.dumps(report, indent=2))
    return path


def main():
    parser = argparse.ArgumentParser(description="Validate the live network against the intent.")
    parser.add_argument("--mode", choices=["full", "ping"], default="full",
                        help="full: all checks (default). ping: reachability only, the baseline.")
    parser.add_argument("--label", default="manual",
                        help="short name for this run, without spaces (e.g. the injected fault)")
    parser.add_argument("--no-save", action="store_true",
                        help="do not write a report file (used for quick health checks)")
    args = parser.parse_args()

    intent = yaml.safe_load(INTENT_FILE.read_text())

    start = time.monotonic()
    results = []
    if args.mode == "full":
        results += run_protocol_checks(intent["routers"], intent.get("standards", {}))
        results += check_loopbacks(intent["routers"], intent["loopback_probes"])
    results += check_reachability(intent["endpoints"])
    duration = round(time.monotonic() - start, 1)

    print_report(results)
    if args.no_save:
        print(f"Duration: {duration} s.")
    else:
        path = save_report(results, args.mode, args.label, duration)
        print(f"Duration: {duration} s. Report saved to {path.relative_to(REPO)}")

    sys.exit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
