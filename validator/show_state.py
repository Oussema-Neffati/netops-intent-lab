"""M3.1: read the intent file, ask every router for its live state, print a summary.

Run from the repo root:  python3 validator/show_state.py
"""

import json
from pathlib import Path

import yaml

from frr import vtysh_json

REPO = Path(__file__).resolve().parent.parent
INTENT_FILE = REPO / "intent" / "network.yml"
RAW_DIR = REPO / "results" / "raw"


def main():
    intent = yaml.safe_load(INTENT_FILE.read_text())
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for name, router in intent["routers"].items():
        print(f"\n=== {name} ===")

        # OSPF neighbours (every router runs OSPF)
        ospf = vtysh_json(name, "show ip ospf neighbor")
        (RAW_DIR / f"{name}-ospf.json").write_text(json.dumps(ospf, indent=2))
        for neighbor_id, entries in ospf.get("neighbors", {}).items():
            for entry in entries:
                print(f"  OSPF  {neighbor_id:<12} {entry.get('nbrState', '?')}")

        # BGP sessions (only routers that have a bgp section in the intent)
        if "bgp" in router:
            bgp = vtysh_json(name, "show bgp summary")
            (RAW_DIR / f"{name}-bgp.json").write_text(json.dumps(bgp, indent=2))
            peers = bgp.get("ipv4Unicast", {}).get("peers", {})
            for peer_ip, peer in peers.items():
                print(
                    f"  BGP   {peer_ip:<12} {peer.get('state', '?'):<12}"
                    f" received={peer.get('pfxRcd', '?')} sent={peer.get('pfxSnt', '?')}"
                    f"  ({peer.get('desc', '')})"
                )


if __name__ == "__main__":
    main()