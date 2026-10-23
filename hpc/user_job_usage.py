#!/usr/bin/env python3
"""Print per-user active job counts and allocated/requested Slurm CPUs.

Run on the login node: python3 user_job_usage.py
Requires Python 3.6+ and squeue. Job array elements count individually.
"""

import os
import subprocess
import sys
from collections import defaultdict


TERMINAL_STATES = {
    "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE", "FAILED",
    "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "REVOKED", "TIMEOUT",
}
# SUSPENDED releases CPUs; STOPPED retains them.
ALLOCATED_STATES = {
    "RUNNING", "CONFIGURING", "COMPLETING", "STOPPED", "RESIZING", "STAGE_OUT",
}


def summarize(output):
    users = defaultdict(lambda: [0, 0, 0, 0, 0])
    seen = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        job_id, user, state, cpu_text = (part.strip() for part in line.split("|"))
        cpus = int(cpu_text)
        if not job_id or not user or cpus < 0:
            raise ValueError("Invalid job record: " + line)
        if job_id in seen or state in TERMINAL_STATES:
            continue
        seen.add(job_id)
        counts = users[user]
        if state == "RUNNING":
            counts[0] += 1
        elif state == "PENDING":
            counts[1] += 1
            counts[4] += cpus
        else:
            counts[2] += 1
        if state in ALLOCATED_STATES:
            counts[3] += cpus
    return users


def main():
    if len(sys.argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    # Ignore interactive squeue filters (e.g. SQUEUE_USERS) for cluster-wide totals.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("SQUEUE_") and k != "SLURM_CLUSTERS"}
    env["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            ["squeue", "--local", "--all", "--array", "--noheader",
             "--states=all", "--format=%i|%u|%T|%C"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, check=True, timeout=30,
        )
        users = summarize(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        print("Job query failed: " + detail.strip(), file=sys.stderr)
        return 1
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    print("Current cluster jobs visible to this account; arrays count per element.")
    print("CPUs are Slurm allocations, not measured CPU utilization.")
    headers = ["USER", "TOTAL_JOBS", "RUNNING", "PENDING", "OTHER",
               "ALLOC_CPUS", "PENDING_CPUS"]
    rows = []
    for user, values in sorted(users.items(), key=lambda item: (-item[1][3], item[0])):
        rows.append([user, sum(values[:3])] + values)
    totals = [sum(row[i] for row in rows) for i in range(1, len(headers))]
    rows.append(["TOTAL"] + totals)
    widths = [max(len(str(row[i])) for row in [headers] + rows)
              for i in range(len(headers))]
    for row in [headers] + rows:
        print("  ".join(str(value).ljust(widths[i]) if i == 0
                        else str(value).rjust(widths[i])
                        for i, value in enumerate(row)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
