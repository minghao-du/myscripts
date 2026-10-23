#!/usr/bin/env python3
"""Show cpu64/cpu128 node resources as a terminal table on the HPC.

Run on the login node: python3 node_resources_table.py
Requires Python 3.6+ and scontrol on PATH. No SSH or companion script needed.
Memory is displayed in GiB, using Slurm configured minus allocated memory.
"""

import datetime
import os
import re
import subprocess
import sys


PARTITIONS = ("cpu64", "cpu128")


def records(output):
    for line in output.splitlines():
        if line.strip():
            yield dict(re.findall(
                r"(?:^|\s)([A-Za-z][A-Za-z0-9_]*)=(.*?)(?=\s+[A-Za-z][A-Za-z0-9_]*=|$)",
                line,
            ))


def number(record, key):
    value = int(record[key])
    if value < 0:
        raise ValueError("Invalid {} for {}".format(key, record.get("NodeName")))
    return value


def build_report(node_output, partition_output):
    partition_states = {r["PartitionName"]: r["State"]
                        for r in records(partition_output)}
    for partition in PARTITIONS:
        if partition not in partition_states:
            raise ValueError("Missing partition: " + partition)
    nodes = []
    seen = set()
    for record in records(node_output):
        memberships = sorted(set(record.get("Partitions", "").split(",")) & set(PARTITIONS))
        if not memberships:
            continue
        name = record["NodeName"]
        if name in seen:
            raise ValueError("Duplicate node: " + name)
        seen.add(name)
        total_cpus = number(record, "CPUTot")
        allocated_cpus = number(record, "CPUAlloc")
        total_memory = number(record, "RealMemory")
        allocated_memory = number(record, "AllocMem")
        unallocated_cpus = max(0, total_cpus - allocated_cpus)
        unallocated_memory = max(0, total_memory - allocated_memory)
        state = record["State"]
        # Conservative candidate flag: preserve flags such as DRAIN, RESERVED,
        # MAINT and NOT_RESPONDING, rather than claiming these nodes are usable.
        candidate = (state in {"IDLE", "MIXED"}
                     and any(partition_states[p] == "UP" for p in memberships)
                     and unallocated_cpus > 0 and unallocated_memory > 0)
        nodes.append({
            "node": name,
            "partitions": memberships,
            "state": state,
            "reason": record.get("Reason"),
            "total_cpus": total_cpus,
            "allocated_cpus": allocated_cpus,
            "unallocated_cpus": unallocated_cpus,
            "total_memory_mib": total_memory,
            "allocated_memory_mib": allocated_memory,
            "unallocated_memory_mib": unallocated_memory,
            "resource_candidate": candidate,
        })
    return {
        "schema_version": 1,
        "queried_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "partition_states": {p: partition_states[p] for p in PARTITIONS},
        "note": "Unallocated = configured minus allocated, clamped to zero. "
                "resource_candidate is a conservative state/resource filter, not a scheduling guarantee. "
                "Reservations, specialized resources, account/QOS limits, partition limits and queue "
                "priority can further restrict allocation. Only account-visible records are included.",
        "nodes": sorted(nodes, key=lambda node: node["node"]),
    }


def query(kind):
    env = {k: v for k, v in os.environ.items() if k != "SLURM_CLUSTERS"}
    env["LC_ALL"] = "C"
    result = subprocess.run(
        ["scontrol", "--local", "--all", "--oneliner", "show", kind],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, check=True, timeout=30,
    )
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.stdout


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
    if len(sys.argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        report = build_report(query("nodes"), query("partitions"))
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        print("Node resource query failed: " + detail.strip(), file=sys.stderr)
        return 1
    print_table(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
