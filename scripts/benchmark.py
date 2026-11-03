"""Opt-in actual OHRBench benchmark. Never benchmarks synthetic/diagnostic tasks.

Run only against an idle local Compose project. Cold means a new artifact namespace
for each worker count, not a flushed OS page cache or an uncached model download.
"""

import argparse
import csv
import json
import subprocess
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen


def api(base, path, body=None):
    request = Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def compose(*args):
    return subprocess.check_output(["docker", "compose", *args], text=True)


def measure(base, spec, count, cache_mode, timeout):
    started = time.monotonic()
    job = api(base, "/api/jobs", spec)
    peak_memory = cpu_sum = samples = 0
    while True:
        job = api(base, f"/api/jobs/{job['id']}")
        # docker stats reports aggregate container usage, including Celery parents.
        ids = compose("ps", "-q", "worker").split()
        if ids:
            rows = subprocess.check_output(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids], text=True
            )
            memory = cpu = 0.0
            for line in rows.splitlines():
                stat = json.loads(line)
                cpu += float(stat["CPUPerc"].rstrip("%"))
                current = stat["MemUsage"].split("/")[0].strip()
                for unit, scale in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024), ("B", 1)):
                    if current.endswith(unit):
                        memory += float(current[: -len(unit)]) * scale
                        break
            peak_memory = max(peak_memory, memory)
            cpu_sum += cpu
            samples += 1
        if job["state"] in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        if time.monotonic() - started > timeout:
            api(base, f"/api/jobs/{job['id']}/cancel", {})
            job = api(base, f"/api/jobs/{job['id']}")
            break
        time.sleep(5)
    elapsed = time.monotonic() - started
    tasks = api(base, f"/api/jobs/{job['id']}/tasks")
    results = api(base, f"/api/jobs/{job['id']}/results")["results"]
    row = {
        "job_id": job["id"],
        "fingerprint": job["fingerprint"],
        "workers": count,
        "cache": cache_mode,
        "state": job["state"],
        "wall_seconds": elapsed,
        "completed_configurations": len(results),
        "configurations_per_second": len(results) / elapsed,
        "retrieval_questions_per_second": sum(r["question_count"] for r in results) / elapsed,
        "peak_worker_container_bytes_sampled": int(peak_memory),
        "mean_worker_cpu_percent_sum_sampled": cpu_sum / samples if samples else None,
        "task_failures": sum(t["state"] == "FAILED" for t in tasks),
        "failed_attempts": sum(a["state"] == "FAILED" for t in tasks for a in t["attempts"]),
        "cache_hit_rate": sum(r["cache_hit"] for r in results) / len(results) if results else 0,
    }
    print(json.dumps(row), flush=True)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-heavy", action="store_true", help="Required: permits real 1/2/4-worker OHRBench runs"
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path, default=Path("var/benchmarks"))
    parser.add_argument("--timeout", type=int, default=86400)
    parser.add_argument("--workers", nargs="+", type=int, choices=[1, 2, 4], default=[1, 2, 4])
    parser.add_argument(
        "--configurations", type=Path, help="JSON list of chunker/noise objects; defaults to all 16"
    )
    args = parser.parse_args()
    if not args.allow_heavy:
        parser.error("Pass --allow-heavy to run the memory-intensive real evaluation")
    configurations = (
        json.loads(args.configurations.read_text())
        if args.configurations
        else [
            {"chunker": c, "noise": n}
            for c in ("fixed", "recursive", "semantic", "structure")
            for n in ("clean", "mild", "moderate", "severe")
        ]
    )
    # Avoid contaminating other jobs. Read all outstanding jobs, including older pages.
    offset = 0
    while True:
        jobs = api(args.base_url, f"/api/jobs?limit=100&offset={offset}")
        if any(j["state"] not in ("COMPLETED", "FAILED", "CANCELLED") for j in jobs):
            raise RuntimeError("Benchmark requires an idle coordinator")
        if len(jobs) < 100:
            break
        offset += 100
    args.output.mkdir(parents=True, exist_ok=True)
    measurements = []
    for workers in args.workers:
        # New cache namespace without deleting any prior results/cache generations.
        namespace = "benchmark-" + uuid.uuid4().hex
        compose("up", "-d", "--wait", "--wait-timeout", "180", "--scale", f"worker={workers}", "worker")
        # Set a cache namespace on the job contract; normal inputs remain unchanged.
        spec = {"mode": "research", "configurations": configurations, "cache_namespace": namespace}
        for cache_mode in ("cold", "warm"):
            row = measure(args.base_url, spec, workers, cache_mode, args.timeout)
            measurements.append(row)
            path = args.output / "measurements.json"
            path.write_text(
                json.dumps(
                    {"scope": "single Docker host; not multi-host scaling", "measurements": measurements},
                    indent=2,
                )
                + "\n"
            )
            if row["state"] != "COMPLETED":
                raise RuntimeError(f"Benchmark failed; measurements retained at {path}")
    for row in measurements:
        reference = next((r for r in measurements if r["workers"] == 1 and r["cache"] == row["cache"]), None)
        row["speedup"] = reference["wall_seconds"] / row["wall_seconds"] if reference else None
        row["parallel_efficiency"] = row["speedup"] / row["workers"] if reference else None
    (args.output / "measurements.json").write_text(
        json.dumps(
            {"scope": "single Docker host; not multi-host scaling", "measurements": measurements}, indent=2
        )
        + "\n"
    )
    with (args.output / "measurements.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(measurements[0]))
        writer.writeheader()
        writer.writerows(measurements)


if __name__ == "__main__":
    main()
