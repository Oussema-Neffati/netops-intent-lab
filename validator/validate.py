"""M3.2: compare the live network with the intent and print a PASS/FAIL report.

Run from the repo root:  python3 validator/validate.py
Exit code: 0 if every check passes, 1 otherwise (useful for automation).
"""

import sys
from pathlib import Path

import yaml

from checks import check_bgp, check_default_route, check_ospf, result

REPO = Path(__file__).resolve().parent.parent
INTENT_FILE = REPO / "intent" / "network.yml"


def run_checks(routers):
    results = []
    for name, router in routers.items():
        try:
            results += check_ospf(name, routers)
            results += check_bgp(name, router)
            results += check_default_route(name, router)
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


def main():
    intent = yaml.safe_load(INTENT_FILE.read_text())
    results = run_checks(intent["routers"])
    print_report(results)
    all_passed = all(r["passed"] for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()