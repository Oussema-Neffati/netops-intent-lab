# Network Design — netops-intent-lab

Status: design for Milestone 1 (hand-written configs). This document is also the
first version of the network's **intent**: the "Expected state" section becomes
the YAML source of truth (M2) and the validator's checks (M3).

## 1. Topology

A company with two sites (A and B) connected through a provider WAN.
Each site is **dual-homed**: its edge router connects to both provider routers,
so losing one WAN link or one provider router does not cut the site off.

```
                     AS 65000 — provider
              wan-p1 ─────────────── wan-p2
              lo 10.0.0.1             lo 10.0.0.2
              │      ╲              ╱      │
         eBGP │       ╲ eBGP  eBGP ╱       │ eBGP
              │        ╲          ╱        │
          a-edge (AS 65001)    b-edge (AS 65002)
              │ OSPF                │ OSPF
          a-core                b-core
           │    │                │    │
         h-a1  h-a2            h-b1  h-b2
```

- **Provider (AS 65000)**: transit only, no hosts. Plays the PE (Provider Edge) role.
- **Edges (a-edge, b-edge)**: each site's border router (CE, Customer Edge).
  Boundary between OSPF (inside) and BGP (outside).
- **Cores (a-core, b-core)**: internal routers and default gateways for the hosts.
- **Hosts**: Linux containers used as traffic endpoints for reachability tests.

10 nodes: 6 FRRouting routers + 4 hosts.

## 2. Addressing plan

The second octet encodes ownership: **10.0.x.x = provider, 10.1.x.x = site A,
10.2.x.x = site B.** All addresses are private (RFC 1918).

| Purpose | Prefix | Addresses |
|---|---|---|
| Provider loopbacks | 10.0.0.0/24 | wan-p1 10.0.0.1/32 · wan-p2 10.0.0.2/32 |
| L1: wan-p1 ↔ wan-p2 | 10.0.1.0/30 | p1 .1 · p2 .2 |
| L2: wan-p1 ↔ a-edge | 10.0.2.0/30 | p1 .1 · a-edge .2 |
| L3: wan-p2 ↔ a-edge | 10.0.3.0/30 | p2 .1 · a-edge .2 |
| L4: wan-p1 ↔ b-edge | 10.0.4.0/30 | p1 .1 · b-edge .2 |
| L5: wan-p2 ↔ b-edge | 10.0.5.0/30 | p2 .1 · b-edge .2 |
| Site A loopbacks | 10.1.0.0/24 | a-edge 10.1.0.1/32 · a-core 10.1.0.2/32 |
| L6: a-edge ↔ a-core | 10.1.1.0/30 | edge .1 · core .2 |
| Site A LAN 1 | 10.1.10.0/24 | gateway a-core .1 · h-a1 .10 |
| Site A LAN 2 | 10.1.20.0/24 | gateway a-core .1 · h-a2 .10 |
| Site B loopbacks | 10.2.0.0/24 | b-edge 10.2.0.1/32 · b-core 10.2.0.2/32 |
| L7: b-edge ↔ b-core | 10.2.1.0/30 | edge .1 · core .2 |
| Site B LAN 1 | 10.2.10.0/24 | gateway b-core .1 · h-b1 .10 |
| Site B LAN 2 | 10.2.20.0/24 | gateway b-core .1 · h-b2 .10 |

**Why loopbacks:** a loopback is a virtual interface that never goes down while
the router is alive. It gives each router a stable identity: OSPF router ID,
BGP peering address, and the address used to test "is this router reachable?".
(Not to be confused with 127.0.0.1, which never leaves the machine.)

**Why /30 on links:** familiar and simple. In production, /31 point-to-point
links would save addresses.

## 3. Interface map

`eth0` on every node is the Containerlab management interface (172.20.20.0/24).
Data-plane links start at `eth1`.

| Node | eth1 | eth2 | eth3 |
|---|---|---|---|
| wan-p1 | wan-p2 | a-edge | b-edge |
| wan-p2 | wan-p1 | a-edge | b-edge |
| a-edge | wan-p1 | wan-p2 | a-core |
| a-core | a-edge | h-a1 | h-a2 |
| b-edge | wan-p1 | wan-p2 | b-core |
| b-core | b-edge | h-b1 | h-b2 |
| hosts | their core | — | — |

The map is symmetrical on purpose: eth1 always points towards the provider
(or, for p1/p2, towards each other). Fewer typos now, simpler templates in M2.

## 4. Routing design

### 4.1 Inside the provider (AS 65000)

- **OSPF area 0** on L1 and both loopbacks.
  *Why:* its only job is to make each provider router's loopback reachable
  from the other, so they can run iBGP between loopbacks.
- **iBGP between loopbacks** (`update-source lo`).
  *Why:* a session between loopbacks does not depend on one physical link; it
  stays up as long as any path exists.
- **`next-hop-self` on the iBGP session.**
  *Why:* every BGP route carries a "next hop" (where to send the traffic). In
  eBGP, the sender puts its own address there; iBGP passes it on unchanged.
  So when wan-p1 tells wan-p2 about site A, the next hop would be 10.0.2.2
  (a-edge's address on L2), which wan-p2 cannot reach, making the route
  unusable. `next-hop-self` makes wan-p1 put its own loopback (10.0.0.1) as
  next hop, which wan-p2 reaches through OSPF. This matters most during
  failover: when wan-p2's own link to a-edge is down, the iBGP route is its
  only path to site A.

### 4.2 Between the provider and the sites (eBGP)

- **Two eBGP sessions per edge**, one to each provider router, over the directly
  connected link addresses.
  *Why:* dual-homing. If one link or one provider router fails, the other
  session still carries the traffic.
- **Each site announces one summary:** site A → 10.1.0.0/16, site B → 10.2.0.0/16.
  *Why:* a summary is one route covering many subnets (10.1.0.0/16 covers every
  address from 10.1.0.0 to 10.1.255.255, so all of site A). The provider's
  table stays small, and adding a LAN inside a site changes nothing outside it.
- **A blackhole static route for each summary** (`ip route 10.1.0.0/16 blackhole`,
  equivalent to Cisco's `Null0`).
  *Why (1):* BGP's `network 10.1.0.0/16` only announces a prefix that exists
  exactly in the routing table. No real subnet is a /16; the static route
  creates it.
  *Why (2):* it prevents loops. By longest prefix match, traffic to real subnets
  (e.g. 10.1.10.0/24) follows the more specific OSPF routes. Traffic to an
  address that does not exist (e.g. 10.1.99.5) only matches the /16 and is
  dropped at the edge, instead of bouncing between the edge and the provider
  until its TTL expires.
- **The provider sends each edge a default route** (`default-originate`), plus
  the other site's summary.
- **Explicit eBGP policies (prefix-lists).** FRR refuses to exchange eBGP routes
  until a policy is applied (`bgp ebgp-requires-policy`). The provider accepts
  only the summary each customer owns: 10.1.0.0/16 from a-edge, 10.2.0.0/16
  from b-edge.
  *Why:* this is what real providers do, so a customer mistake cannot leak
  wrong routes into the WAN.

### 4.3 Inside each site (OSPF area 0)

- **Edge ↔ core link uses `ip ospf network point-to-point`.**
  *Why:* a DR/BDR election is useless on a link with only two routers; it only
  adds delay and an extra LSA type (observed in the frr01 example).
- **Loopbacks advertised deliberately.**
  *Why:* in the frr01 example, loopbacks were configured but not advertised, so
  they were unreachable although the hosts expected them to be.
- **Host LANs advertised as passive interfaces.**
  *Why:* the LAN must be known to OSPF, but there is no router on it, so no
  hellos are sent towards the hosts.
- **The edge injects the default route into OSPF with `default-information
  originate`, without `always`.**
  *Why:* the edge then advertises a default only while it actually has one from
  BGP. If both WAN links die, the default disappears from the core, and the
  core stops sending traffic into a dead end.

### 4.4 Hosts

- Each host: its address on eth1 and a route to **10.0.0.0/8 via its gateway**.
  *Why:* the hosts' default route already points to management (eth0), so the
  data network is reached through a more specific route.

### 4.5 What the design deliberately leaves out

- **No NAT and no internet access.** The sites talk over a private WAN with
  end-to-end routing, like a real private WAN or MPLS service. NAT would change
  addresses in transit and complicate the reachability checks.
- **No IPv6, no firewall node, no monitoring stack** in the minimum version
  (monitoring and an nftables security node are planned extensions).

## 5. Expected state (intent, version 0)

| Check | Expected |
|---|---|
| OSPF adjacencies | 3, all Full: p1–p2, a-edge–a-core, b-edge–b-core |
| BGP sessions | 5, all Established: p1–p2 (iBGP) + 4 eBGP |
| a-edge receives | 10.2.0.0/16 and 0.0.0.0/0, each from **both** wan-p1 and wan-p2 |
| b-edge receives | 10.1.0.0/16 and 0.0.0.0/0, each from **both** wan-p1 and wan-p2 |
| Provider accepts | only 10.1.0.0/16 from a-edge and only 10.2.0.0/16 from b-edge |
| Cores have | a default route via their edge, learned by OSPF |
| Reachability | every host reaches every other host (4×4 matrix) + all loopbacks |

Note: "receives each prefix from both providers" is a check a ping cannot make.
With one eBGP session down, every ping still succeeds, but the site has lost
its redundancy.

## 6. New concepts in this design (learning notes)

CCNA concepts used: single-area OSPF, router ID, DR/BDR, OSPF network types,
static and default routes, summarization, longest prefix match, loopbacks.

Beyond CCNA (learned in this project): eBGP and iBGP, next-hop-self,
`default-originate`, BGP prefix-list policies, blackhole routes for summaries,
dual-homing. Each one is demonstrated in the lab by configuring it, removing it
on purpose, and observing what breaks (see `journal.md`).