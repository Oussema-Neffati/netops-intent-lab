# Lab Journal — netops-intent-lab

## 2026-10-26 — M0: environment setup
- Did: installed WSL2 platform (WSL 3.0.3), capped WSL at 6 GB / 4 CPUs,
  installed WSL-Containerlab 0.82.0 (Docker 27.5.1).
- Decision: lab stays on C: (93 GB free) instead of the external NVMe.
- Problem: first `wsl --install` failed ("requires elevation").
- Fix: re-ran it in an administrator PowerShell.
- Notes: idle WSL memory ≈ 460 MiB.