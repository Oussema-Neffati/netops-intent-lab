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


def check_bgp(name, router):
    """Each BGP neighbour in the intent must be Established and send the expected prefixes."""
    if "bgp" not in router:
        return []
    peers = vtysh_json(name, "show bgp summary").get("ipv4Unicast", {}).get("peers", {})
    results = []
    for neighbor in router["bgp"]["neighbors"]:
        ip, label = neighbor["ip"], neighbor["description"]
        state = peers.get(ip, {}).get("state", "absent")
        results.append(result(name, f"BGP session with {label} ({ip})", "Established", state))

        if "expect_prefixes" in neighbor:
            routes = vtysh_json(name, f"show bgp ipv4 unicast neighbors {ip} routes")
            received = sorted(routes.get("routes", {}).keys())
            results.append(
                result(name, f"Prefixes received from {label}", sorted(neighbor["expect_prefixes"]), received)
            )
    return results


def check_default_route(name, router):
    """Routers with expect_default_route must use a default route from that protocol."""
    if "expect_default_route" not in router:
        return []
    entries = vtysh_json(name, "show ip route 0.0.0.0/0").get("0.0.0.0/0", [])
    selected = [entry for entry in entries if entry.get("selected")]
    protocol = selected[0].get("protocol", "?") if selected else "absent"
    return [result(name, "Default route source", router["expect_default_route"], protocol)]


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