#!/usr/bin/env python3
"""Show HPC node resources as a terminal table using the deployed JSON query.

Run locally: python3 node_resources_table.py [--host zju_hpc_jump]
Requires SSH access and ~/.local/lib/zju-hpc/node_resources.py on the HPC.
"""

import argparse
import json
import subprocess
import sys


def print_table(report):
    print("HPC node resources | {}".format(report["queried_at"]))
    print("Memory: GiB; FREE = configured minus allocated (Slurm).")
    print("CANDIDATE is a state/resource filter; immediate scheduling is not guaranteed.")
    for partition, state in sorted(report["partition_states"].items()):
        print("{}: {}".format(partition, state))
    headers = ["NODE", "PARTITION", "STATE", "FREE_CPU", "TOTAL_CPU",
               "FREE_GiB", "TOTAL_GiB", "CANDIDATE"]
    rows = []
    for node in sorted(report["nodes"], key=lambda n: (n["partitions"], n["node"])):
        rows.append([
            node["node"], ",".join(node["partitions"]), node["state"],
            node["unallocated_cpus"], node["total_cpus"],
            "{:.1f}".format(node["unallocated_memory_mib"] / 1024),
            "{:.1f}".format(node["total_memory_mib"] / 1024),
            "yes" if node["resource_candidate"] else "no",
        ])
    widths = [max(len(str(row[i])) for row in [headers] + rows)
              for i in range(len(headers))]
    print()
    for row in [headers] + rows:
        print("  ".join(str(value).rjust(widths[i]) if 3 <= i <= 6
                        else str(value).ljust(widths[i])
                        for i, value in enumerate(row)))
    print("\n{} nodes; {} resource candidates.".format(
        len(rows), sum(bool(n["resource_candidate"]) for n in report["nodes"])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="zju_hpc_jump", help="SSH host alias (default: zju_hpc_jump)")
    args = parser.parse_args()
    if args.host.startswith("-"):
        parser.error("host must be an SSH hostname or alias")
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", args.host,
             'LC_ALL=C bash -lc "python3 ~/.local/lib/zju-hpc/node_resources.py"'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, check=True, timeout=120,
        )
        report = json.loads(result.stdout)
        print_table(report)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        print("Node resource query failed: " + detail.strip(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
