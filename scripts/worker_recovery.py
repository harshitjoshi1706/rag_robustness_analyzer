"""Opt-in destructive local TEST of worker-container loss; no historical files changed.

Only use an isolated, idle Compose project with fixture mode enabled. This script
kills that project's workers, restarts them, then verifies a real smoke job recovers.
"""

import argparse
import json
import subprocess
import time
from urllib.request import Request, urlopen


def api(base, path, body=None):
    request = Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-worker-kill", action="store_true")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if not args.allow_worker_kill:
        parser.error("Pass --allow-worker-kill to terminate the isolated project's workers")
    jobs = api(args.base_url, "/api/jobs?limit=100")
    if any(j["state"] not in ("COMPLETED", "FAILED", "CANCELLED") for j in jobs):
        raise RuntimeError("Project must be idle before the crash test")
    # Fresh namespace ensures the task actually loads a model and builds an index.
    spec = {
        "mode": "smoke",
        "configurations": [{"chunker": "semantic", "noise": "clean"}],
        "cache_namespace": f"recovery-{int(time.time())}",
    }
    job = api(args.base_url, "/api/jobs", spec)["id"]
    until = time.monotonic() + args.timeout
    killed = False
    while time.monotonic() < until:
        tasks = api(args.base_url, f"/api/jobs/{job}/tasks")
        if not killed and any(t["state"] == "RUNNING" for t in tasks):
            subprocess.run(["docker", "compose", "kill", "-s", "SIGKILL", "worker"], check=True)
            subprocess.run(["docker", "compose", "start", "worker"], check=True)
            killed = True
        state = api(args.base_url, f"/api/jobs/{job}")["state"]
        if state == "COMPLETED":
            assert killed and tasks[0]["attempt"] >= 2, tasks
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "job": job,
                        "attempts": tasks[0]["attempt"],
                        "scope": "single-host real worker-container crash/restart",
                    }
                )
            )
            return
        if state in ("FAILED", "CANCELLED"):
            raise AssertionError(tasks)
        time.sleep(0.5)
    raise TimeoutError(api(args.base_url, f"/api/jobs/{job}/tasks"))


if __name__ == "__main__":
    main()
