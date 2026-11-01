# netops-intent-lab

**Status: Milestone 1 complete — network built and verified by hand.
Next: automated deployment (Ansible) and intent validation (Python).**

## Engineering question
In a dual-homed two-site routed network, can automated intent-based
validation (desired state in YAML compared against live protocol state)
detect and localise faults that a ping-based check misses, and how long
do a full deploy → verify cycle and a WAN failover take?

## The network
A company with two sites connected through a provider WAN. Each site's edge
router is dual-homed to both provider routers.

- **10 nodes:** 6 FRRouting routers + 4 Linux hosts, built with Containerlab.
- **Inside each site:** OSPF area 0 (point-to-point links, passive host LANs,
  loopbacks advertised); the edge injects a default route towards the core.
- **Provider core:** OSPF between the two provider routers, iBGP between loopbacks.
- **Between sites and provider:** eBGP; each site announces one /16 summary and
  receives a default route; prefix-lists filter what each side accepts.

Full design, addressing plan and the reasoning behind each choice:
[`docs/design.md`](docs/design.md).

## Verified state (Milestone 1, checked by hand)
| Check | Result |
|---|---|
| Links and interface addressing | 11/11 links pass |
| OSPF adjacencies | 3/3 Full (provider core, site A, site B) |
| BGP sessions | 5/5 Established (1 iBGP + 4 eBGP) |
| Each edge receives the default and the other site's summary from both providers | Yes (both paths used: ECMP) |
| Cross-site host reachability | All tested pairs succeed (5 router hops) |

## Run it
Requirements: Linux (or WSL2) with Docker and Containerlab.
```bash
cd topology
clab deploy -t netops.clab.yml      # build the lab (~30 s)
clab destroy -t netops.clab.yml --cleanup
```

## Repository layout
```
topology/   Containerlab topology (and viewer layout)
configs/    FRRouting configuration per router (hand-written in M1)
docs/       Design document
journal.md  Dated record of work, problems and fixes
```

## Environment
Windows 11 · WSL2 · WSL-Containerlab 0.82.0 · Docker 27.5.1 ·
FRRouting 10.7.1 · whole lab ≈ 220 MiB RAM (measured with `docker stats`)

## Roadmap
- [x] M0 — Environment and first lab
- [x] M1 — Own topology, hand-written configs, OSPF/BGP up
- [ ] M2 — YAML source of truth → Jinja2 templates → Ansible deployment
- [ ] M3 — Python validator: intent vs live state
- [ ] M4 — Fault injection (8 faults) and failover measurement
- [ ] M5 — Results, limitations, reproduction guide

## Limitations
No NAT or internet access (private WAN only), no IPv6, no firewall node,
no monitoring stack in the minimum version.