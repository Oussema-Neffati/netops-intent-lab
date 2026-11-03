"""Helpers to read live state from the FRR routers running in Containerlab."""

import json
import subprocess

LAB_PREFIX = "clab-netops-"


def vtysh_json(router, command):
    """Run a FRR 'show ...' command with JSON output and return it as Python data.

    Example: vtysh_json("a-edge", "show bgp summary") runs
    docker exec clab-netops-a-edge vtysh -c "show bgp summary json"
    """
    result = subprocess.run(
        ["docker", "exec", LAB_PREFIX + router, "vtysh", "-c", command + " json"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{router}: '{command}' failed: {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output:
        return {}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        # FRR printed text instead of JSON (for example "% BGP instance not found")
        first_line = output.splitlines()[0]
        raise RuntimeError(f"{router}: '{command}' did not return JSON: {first_line}")