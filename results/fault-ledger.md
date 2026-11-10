# Fault ledger

| # | Fault | CCNA topic | Ping only | Validator |
|---|---|---|---|---|
| 1 | WAN link W1 shut down (isp1 eth1, towards a-edge1) | Interface status, redundancy | **missed** | detected |
| 2 | passive-interface on a router-to-router link (a-edge1 eth2, link A1) | OSPF passive interfaces | **missed** | detected |
| 3 | MTU lowered to 1400 on a-edge2 eth2 (link A3, a-core1 keeps its MTU) | OSPF adjacency requirements (MTU) | **missed** | detected |
| 4 | hello interval 5 s on b-edge1 eth2 (link B1, b-core1 keeps 10 s) | OSPF adjacency requirements (hello/dead timers) | **missed** | detected |
| 5 | b-core2 puts link B4 in area 1 (b-edge2 keeps area 0) | OSPF areas | **missed** | detected |
| 6 | a-core1 no longer advertises VLAN 20 (10.1.20.0/24) | OSPF configuration (network statement) | **missed** | detected |
| 7 | b-core1 no longer advertises its loopback 10.2.0.3/32 | OSPF configuration (loopbacks) | **missed** | detected |
| 8 | h-b2 sends traffic to a wrong gateway (10.2.20.99) | IP addressing (default gateway) | detected | detected |
| 9 | a-core1 loses its trunk to a-sw1: a-core2 must take over the gateway | First-hop redundancy (VRRP) | **missed** | detected |

**Faults detected: validator 9/9, ping only 1/9.**
