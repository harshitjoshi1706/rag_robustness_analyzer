"""Verify durable pending work survives a coordinator stop/start in an idle test project."""

import argparse
import json
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-api-restart", action="store_true")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    if not args.allow_api_restart:
        parser.error("Pass --allow-api-restart to stop/start the isolated project's API")
    with urlopen(args.base_url + "/api/jobs?limit=100", timeout=10) as response:
        jobs = json.load(response)
    if any(j["state"] not in ("COMPLETED", "FAILED", "CANCELLED") for j in jobs):
        raise RuntimeError("Project must be idle before coordinator recovery test")
    subprocess.run(["docker", "compose", "stop", "api"], check=True)
    try:
        code = (
            "from platform_eval.config import Settings; from platform_eval.db import Store; "
            "from platform_eval.inputs import freeze; s=Settings(); "
            "assert s.allow_fixture, 'Use an isolated fixture-enabled project'; "
            "spec={'mode':'fixture','configurations':[{'chunker':'fixed','noise':'clean'}]}; "
            "print(Store(s).submit(spec,freeze(s,'fixture')))"
        )
        job = subprocess.check_output(
            ["docker", "compose", "exec", "-T", "worker", "python", "-c", code], text=True
        ).strip()
    finally:
        subprocess.run(["docker", "compose", "start", "api"], check=True)
    until = time.monotonic() + 60
    while time.monotonic() < until:
        try:
            with urlopen(f"{args.base_url}/api/jobs/{job}", timeout=5) as response:
                state = json.load(response)["state"]
            if state == "COMPLETED":
                print(
                    json.dumps(
                        {
                            "status": "passed",
                            "job": job,
                            "scope": "pending durable work recovered after actual coordinator restart",
                        }
                    )
                )
                return
            if state == "FAILED":
                raise AssertionError("Recovered job failed")
        except (URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.5)
    raise TimeoutError("Coordinator did not resume persisted pending work")


if __name__ == "__main__":
    main()
