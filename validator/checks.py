"""M3.2 checks: compare the live state of one router with its intent.

Every check returns a list of results. A result says which router, what was
checked, what the intent expects, what the router actually reports, and
whether the two match.
"""

import ipaddress

from frr import ping, vtysh_json


def result(router, check, expected, actual):
    return {
        "router": router,
        "check": check,
        "expected": expected,
        "actual": actual,
        "passed": expected == actual,
    }


def expected_ospf_neighbors(name, routers):
    """Router IDs this router should see as OSPF neighbours, derived from the intent.

    Rule: two routers are OSPF neighbours when each has an OSPF point-to-point
    interface in the same subnet.
    """
    my_subnets = [
        ipaddress.ip_interface(intf["ip"]).network
        for intf in routers[name]["interfaces"]
        if intf.get("ospf_p2p")
    ]
    expected = set()
    for other_name, other in routers.items():
        if other_name == name:
            continue
        for intf in other["interfaces"]:
            if intf.get("ospf_p2p") and ipaddress.ip_interface(intf["ip"]).network in my_subnets:
                expected.add(other["ospf"]["router_id"])
    return expected


def check_ospf(name, routers):
    """Each expected OSPF neighbour must be present and Full."""
    if "ospf" not in routers[name]:
        return []
    live = vtysh_json(name, "show ip ospf neighbor").get("neighbors", {})
    results = []
    for router_id in sorted(expected_ospf_neighbors(name, routers)):
        entries = live.get(router_id, [])
        if isinstance(entries, dict):  # some FRR versions return one dict, not a list
            entries = [entries]
        if entries:
            entry = entries[0]
            state = entry.get("converged") or entry.get("nbrState", "?").split("/")[0]
        else:
            state = "absent"
        results.append(result(name, f"OSPF neighbour {router_id}", "Full", state))
    return results


def bfd_peers(name):
    """BFD session status per peer address, e.g. {"10.0.2.1": "up"}."""
    data = vtysh_json(name, "show bfd peers")
    if isinstance(data, dict):  # some FRR versions wrap the list in an object
        data = data.get("peers", [])
    return {peer.get("peer"): peer.get("status", "?") for peer in data}


def check_bgp(name, router, standards=None):
    """Each BGP neighbour in the intent must be Established and send the expected prefixes.

    eBGP neighbours (different AS) must also have an up BFD session when the
    network standard ebgp_bfd is enabled.
    """
    if "bgp" not in router:
        return []
    standards = standards or {}
    peers = vtysh_json(name, "show bgp summary").get("ipv4Unicast", {}).get("peers", {})
    bfd = bfd_peers(name) if standards.get("ebgp_bfd") else {}
    results = []
    for neighbor in router["bgp"]["neighbors"]:
        ip, label = neighbor["ip"], neighbor["description"]
        state = peers.get(ip, {}).get("state", "absent")
        results.append(result(name, f"BGP session with {label} ({ip})", "Established", state))

        if standards.get("ebgp_bfd") and neighbor["remote_as"] != router["bgp"]["asn"]:
            results.append(result(name, f"BFD with {label} ({ip})", "up", bfd.get(ip, "absent")))

        if "expect_prefixes" in neighbor:
            routes = vtysh_json(name, f"show bgp ipv4 unicast neighbors {ip} routes")
            received = sorted(routes.get("routes", {}).keys())
            results.append(
                result(name, f"Prefixes received from {label}", sorted(neighbor["expect_prefixes"]), received)
            )
    return results


def check_routes(name, router):
    """Each prefix in expect_routes must be learned from the expected protocol over
    the expected number of equal-cost paths (redundancy check)."""
    results = []
    for prefix, want in router.get("expect_routes", {}).items():
        entries = vtysh_json(name, f"show ip route {prefix}").get(prefix, [])
        selected = [entry for entry in entries if entry.get("selected")]
        if selected:
            hops = [h for h in selected[0].get("nexthops", []) if h.get("active", True)]
            actual = f"{selected[0].get('protocol', '?')} x{len(hops)}"
        else:
            actual = "absent"
        expected = f"{want['protocol']} x{want['paths']}"
        results.append(result(name, f"Route {prefix} (paths)", expected, actual))
    return results


def check_vrrp(name, router):
    """Each VRRP group must be in its expected role (Master or Backup)."""
    expected = router.get("expect_vrrp", {})
    if not expected:
        return []
    data = vtysh_json(name, "show vrrp")
    if isinstance(data, dict):
        data = data.get("vrrp", data.get("routers", []))
    states = {}
    for vr in data:
        status = vr.get("v4", {}).get("status") or vr.get("status", "?")
        states[int(vr.get("vrid", -1))] = status
    return [result(name, f"VRRP group {vrid} role", role, states.get(int(vrid), "absent"))
            for vrid, role in expected.items()]


def check_reachability(hosts):
    """Every host must reach every other host (the reachability matrix)."""
    results = []
    for source in hosts:
        for target, target_data in hosts.items():
            if source == target:
                continue
            ip = target_data["ip"].split("/")[0]
            reachable = "reachable" if ping(source, ip) else "unreachable"
            results.append(result(source, f"Ping {target} ({ip})", "reachable", reachable))
    return results


def check_loopbacks(routers, probes):
    """Every site router loopback must be reachable from each probe host."""
    results = []
    for source in probes:
        for name, router in routers.items():
            if "ospf" not in router:  # provider loopbacks are not routed between providers
                continue
            ip = router["loopback"].split("/")[0]
            reachable = "reachable" if ping(source, ip) else "unreachable"
            results.append(result(source, f"Ping {name} loopback ({ip})", "reachable", reachable))
    return results