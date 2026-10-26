# netops-intent-lab

**Status: work in progress (Milestone 0: environment setup).**

## Engineering question
In a dual-homed two-site routed network, can automated intent-based
validation (desired state in YAML compared against live protocol state)
detect and localise faults that a ping-based check misses, and how long
do a full deploy → verify cycle and a WAN failover take?

## Planned stack
Containerlab · FRRouting · Ansible · Python · Git

## Environment
Windows 11 · WSL2 · WSL-Containerlab 0.82.0 · Docker 27.5.1 · 6 GB RAM cap