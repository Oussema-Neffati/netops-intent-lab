# Lab Journal — netops-intent-lab

## 2026-10-26 — M0: environment setup
- Did: installed WSL2 platform (WSL 3.0.3), capped WSL at 6 GB / 4 CPUs,
  installed WSL-Containerlab 0.82.0 (Docker 27.5.1).
- Decision: lab stays on C: (93 GB free) instead of the external NVMe.
- Problem: first `wsl --install` failed ("requires elevation").
- Fix: re-ran it in an administrator PowerShell.
- Notes: idle WSL memory ≈ 460 MiB.

## 2026-10-28 — M0: first lab (frr01)
- Did: deployed the official frr01 example (3 FRR 10.7.1 routers, OSPF, 3 hosts).
  Deploy took ~29 s, including image pulls.
- Measured: FRR ≈ 20 MiB/node, multitool host ≈ 3 MiB/node (docker stats).
- Observed: OSPF Full on all links; ECMP to 192.168.3.0/24; PC1→PC3 ping OK (TTL 62).
- Finding: PC2 cannot reach 10.10.10.1. Loopbacks are not advertised in OSPF,
  although the hosts' static routes expect them to be. Config ≠ intent.
- Lessons for M1: advertise loopbacks deliberately; use OSPF point-to-point on
  router links; test data-plane addresses only, never management (eth0).

  ## 2026-10-29 — M1 step 2: topology and addressing
- Did: 10-node topology (6 FRR + 4 hosts); interface addresses on all routers.
- Verified: 11/11 links pass ping; cabling matches the interface map.
- Mistake caught before deploy: b-edge eth1/eth2 swapped (right addresses, wrong ports).
- Prediction 1: wan-p1 → 10.0.0.2 fails; local kernel has no route ("sendto: Network unreachable").
- Prediction 2: h-a1 → h-a2 works without routing (TTL 63); a-core is connected to both LANs.
- Measured: routers 29–45 MiB with ospfd+bgpd; whole lab ≈ 220 MiB.
- Problem: files saved with CRLF. Fix: VS Code files.eol = \n, sed conversion, .gitattributes.

## 2026-11-01 — M1 step 3: provider core
- Bug: wan-p2 had `network 10.0.0.1/32` (wan-p1's loopback) instead of 10.0.0.2/32.
- Symptoms: OSPF Full, but no OSPF routes on wan-p1 → loopback unreachable → BGP stuck in Active.
- Lesson: adjacency up ≠ correct routes. FRR accepted the wrong line silently.
- Validator check idea: "each router has an OSPF route to every expected loopback".

- eBGP between both edges and both provider routers; summaries, default route, prefix-lists.
- Verified: 5/5 BGP sessions, each edge gets default + other site from both providers,
  cross-site pings OK (TTL 59 = 5 router hops).
- Observation: WAN is active-active (ECMP over both providers), not active-standby.
- M1 complete.