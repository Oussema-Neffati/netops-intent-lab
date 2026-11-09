# Network Design: netops-intent-lab

Status: design v2. v1 (one edge and one core per site, one provider) is archived
in Git history and in `results/archive-v1/`. v2 removes every single point of
failure identified in the v1 review.

## 1. Topology

A company with two sites (A and B), each connected to **two independent providers**.
Inside each site, **every device has a partner**: two edge routers, two core
routers, gateway redundancy (VRRP) and an access switch with VLANs.

```
          isp1 (AS 65010)                     isp2 (AS 65020)
           │          └──────────┐   ┌──────────┘          │
       W1  │                 W3  │   │  W4                 │ W2
           │                     │   │                     │
   ┌───── a-edge1 ── iBGP ── a-edge2 ┐  ┌ b-edge1 ── iBGP ── b-edge2 ─────┐
   │        │   ╲          ╱   │     │  │   │   ╲          ╱   │          │
   │        │     ╲      ╱     │     │  │   │     ╲      ╱     │          │
   │      a-core1 ═VRRP═ a-core2     │  │ b-core1 ═VRRP═ b-core2          │
   │          ╲         ╱            │  │     ╲         ╱                 │
   │     802.1Q trunks to a-sw1      │  │  802.1Q trunks to b-sw1         │
   │        VLAN 10: h-a1            │  │   VLAN 10: h-b1                 │
   │        VLAN 20: h-a2            │  │   VLAN 20: h-b2                 │
   └──────── Site A · AS 65001 ──────┘  └──────── Site B · AS 65002 ──────┘
```

- **Providers:** isp1 and isp2 are independent (different AS numbers, no link
  between them). Each connects one edge router in each site.
- **Edge routers:** each site has two, each connected to a different provider.
  They exchange routes with iBGP between their loopbacks.
- **Core routers:** each site has two, each connected to both edges (full mesh,
  4 OSPF links per site). They are the hosts' gateways, made redundant with VRRP.
- **Access switch:** one per site, carrying VLAN 10 and VLAN 20 on 802.1Q trunks
  to both cores. Implemented as a Linux container with one bridge per VLAN.
- **Hosts:** Linux containers, one per VLAN, using the VRRP virtual IP as gateway.

16 nodes: 10 FRRouting routers, 2 switches, 4 hosts.

## 2. Addressing plan

Second octet = owner: **10.0 = providers, 10.1 = site A, 10.2 = site B.**

| Purpose | Prefix | Addresses |
|---|---|---|
| Provider loopbacks | 10.0.0.0/24 | isp1 .1 · isp2 .2 |
| W1 isp1 ↔ a-edge1 | 10.0.1.0/30 | isp .1 · edge .2 |
| W2 isp2 ↔ a-edge2 | 10.0.2.0/30 | isp .1 · edge .2 |
| W3 isp1 ↔ b-edge1 | 10.0.3.0/30 | isp .1 · edge .2 |
| W4 isp2 ↔ b-edge2 | 10.0.4.0/30 | isp .1 · edge .2 |
| Site A loopbacks | 10.1.0.0/24 | a-edge1 .1 · a-edge2 .2 · a-core1 .3 · a-core2 .4 |
| A1 a-edge1 ↔ a-core1 | 10.1.1.0/30 | edge .1 · core .2 |
| A2 a-edge1 ↔ a-core2 | 10.1.1.4/30 | edge .5 · core .6 |
| A3 a-edge2 ↔ a-core1 | 10.1.1.8/30 | edge .9 · core .10 |
| A4 a-edge2 ↔ a-core2 | 10.1.1.12/30 | edge .13 · core .14 |
| Site A VLAN 10 | 10.1.10.0/24 | VIP .1 · a-core1 .2 · a-core2 .3 · h-a1 .10 |
| Site A VLAN 20 | 10.1.20.0/24 | VIP .1 · a-core1 .2 · a-core2 .3 · h-a2 .10 |
| Site B | 10.2.x.x | same structure as site A (B1–B4, VLANs 10 and 20) |

**Why /30 on links:** kept on purpose for readability (the CCNA convention).
In production, /31 point-to-point links (RFC 3021) would halve their address use.

## 3. Interface map

`eth0` is the Containerlab management interface on every node.

| Node | eth1 | eth2 | eth3 | eth4 |
|---|---|---|---|---|
| isp1 | a-edge1 (W1) | b-edge1 (W3) | | |
| isp2 | a-edge2 (W2) | b-edge2 (W4) | | |
| x-edge1 | isp1 | x-core1 | x-core2 | |
| x-edge2 | isp2 | x-core1 | x-core2 | |
| x-core1 / x-core2 | x-edge1 | x-edge2 | trunk to x-sw1 (eth3.10, eth3.20) | |
| x-sw1 | trunk x-core1 | trunk x-core2 | access VLAN 10 (h-x1) | access VLAN 20 (h-x2) |

## 4. Routing and switching design

### 4.1 Providers
- Each provider runs eBGP with one edge per site, sends each a **default route**
  and the other site's summary, and accepts only the summary each customer owns
  (prefix-lists).
- The two providers are independent: no link, no shared routing. Losing one
  provider completely leaves every site reachable through the other.

### 4.2 Edge routers
- **eBGP** to their provider; **iBGP between the two edges of a site**, over
  loopbacks (`update-source lo`, `next-hop-self`).
  *Why iBGP:* if a-edge1 loses its provider, it still learns site B's summary
  and the default route from a-edge2, so traffic arriving at a-edge1 is not
  dropped.
- Each edge announces the site summary (10.1.0.0/16), made announceable by a
  **blackhole static route**, and injects a default route into OSPF with
  `default-information originate` (no `always`).

### 4.3 Inside each site (OSPF area 0)
- **Full mesh edge ↔ core:** 4 point-to-point links. Losing any one link or any
  one router leaves at least one path.
- **Equal-cost paths:** each core reaches the default route through both edges,
  and each edge reaches each VLAN through both cores (ECMP). The validator checks
  that these paths really are 2 (redundancy, not only reachability).
- **Passive by default:** every interface is passive except the router-to-router
  links, derived by the template from `ospf_p2p: true`.

### 4.4 Gateway redundancy (VRRP)
- Each VLAN has a **virtual gateway IP (.1)** shared by both cores with VRRP.
  The core with the higher priority (core1, 150) is **Master** and answers for
  the virtual IP; core2 (100) is **Backup** and takes over if core1 fails.
- VRRP is the open standard equivalent of Cisco's HSRP.
- Implementation detail (Linux/FRR): the virtual IP lives on a macvlan interface
  with the VRRP virtual MAC (00:00:5e:00:01:VRID), created at deploy time.

### 4.5 Access switching
- One bridge per VLAN; trunk ports carry VLANs 10 and 20 as 802.1Q
  subinterfaces; access ports are untagged members of one VLAN.

## 5. Network standards (applied to every router by the template)

| Standard | Where | Why |
|---|---|---|
| OSPF MD5 authentication | every router-to-router link | an unauthenticated device cannot join OSPF or inject routes |
| BGP TCP-MD5 password | every BGP session | protects sessions against spoofed TCP packets and resets |
| BFD | every eBGP session | detects a failed neighbour in under a second instead of the BGP hold timer (180 s) |
| Maximum-prefix 10 | every eBGP session | a neighbour sending too many routes (a leak) is shut down |
| Passive by default | OSPF | no hellos towards hosts |

Secrets in the intent file are **lab-only values**; in production they would
come from a vault (e.g. Ansible Vault).

## 6. Scope and remaining assumptions

v2 removes the single points of failure of v1. Still deliberately out of scope:
- **One access switch per site** (a switch stack or a second switch would remove
  this last single point of failure for the hosts).
- Internet edge and NAT, firewalls and security zones, wireless, remote access
  (VPN/ZTNA), IPv6, QoS.
- **Management plane:** routers are reached with `docker exec`; no NTP, syslog,
  AAA or SNMP inside the lab.

## 7. Expected state (intent v2): 96 checks

| Check | Count | Expected |
|---|---|---|
| OSPF neighbours (derived from the p2p subnets) | 16 | Full, authenticated |
| BGP sessions (eBGP + iBGP) | 12 | Established |
| Prefixes received per BGP neighbour | 12 | exactly the expected list |
| BFD sessions (eBGP, both sides) | 8 | up |
| Redundant routes (`expect_routes`) | 12 | 2 equal-cost OSPF paths |
| VRRP roles | 8 | core1 Master, core2 Backup |
| Site router loopbacks from each site | 16 | reachable |
| Host-to-host matrix | 12 | reachable |

The redundancy checks matter most in v2: with this much redundancy, almost no
single failure breaks a ping, so only state checks can see that a backup path,
a session or a gateway role has been lost.

## 8. Concepts used

CCNA: OSPF (point-to-point, passive, authentication, ECMP), static and default
routes, summarization, VLANs and 802.1Q trunks, first-hop redundancy (VRRP/HSRP),
loopbacks.
Beyond CCNA: eBGP and iBGP, next-hop-self, prefix-list policies, BFD,
maximum-prefix, blackhole routes for summaries, multihoming to two providers.
