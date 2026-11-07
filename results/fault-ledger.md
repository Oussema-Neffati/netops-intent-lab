# Fault ledger

| # | Fault | CCNA topic | Ping only | Validator | Validator failed checks |
|---|---|---|---|---|---|
| 1 | WAN link L2 shut down (wan-p1 eth2, towards a-edge) | Interface status, redundancy | **missed** | detected | 5/52 |
| 2 | passive-interface on the provider core link (wan-p1 eth1) | OSPF passive interfaces | **missed** | detected | 4/52 |
| 3 | MTU lowered to 1400 on wan-p1 eth1 (neighbour keeps its MTU) | OSPF adjacency requirements (MTU) | **missed** | detected | 4/52 |
| 4 | hello interval 5 s on a-edge eth3 (a-core keeps 10 s) | OSPF adjacency requirements (hello/dead timers) | detected | detected | 17/52 |
| 5 | b-core puts link L7 in area 1 (b-edge keeps area 0) | OSPF areas | detected | detected | 17/52 |
| 6 | a-core no longer advertises LAN 10.1.20.0/24 (h-a2) | OSPF configuration (network statement) | detected | detected | 4/52 |
| 7 | b-core no longer advertises its loopback 10.2.0.2/32 | OSPF configuration (loopbacks) | **missed** | detected | 1/52 |
| 8 | h-b2 sends traffic to a wrong gateway (10.2.20.99) | IP addressing (default gateway) | detected | detected | 6/52 |

**Faults detected: validator 8/8, ping only 4/8.**
