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