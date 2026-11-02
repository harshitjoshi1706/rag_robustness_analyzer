"""Run inside the API container with RAG_ALLOW_FIXTURE=1. No full dataset needed."""

import argparse
import json
import time
import uuid
from pathlib import Path

from platform_eval.celery_app import app
from platform_eval.config import Settings
from platform_eval.db import Store
from platform_eval.inputs import freeze
from services.platform_client import PlatformClient


def wait_for(client, job, expected="COMPLETED", timeout=180):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        current = client.call(f"/api/jobs/{job}")
        if current["state"] == expected:
            return current
        if current["state"] in ("FAILED", "CANCELLED"):
            raise AssertionError(client.call(f"/api/jobs/{job}/tasks"))
        time.sleep(0.5)
    raise TimeoutError(client.call(f"/api/jobs/{job}/tasks"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true")
    args = parser.parse_args()
    client = PlatformClient("http://api:8000")
    settings = Settings()
    store = Store(settings)
    spec = {"mode": "fixture", "configurations": [{"chunker": "fixed", "noise": "clean"}]}
    client.call("/ready")
    key = str(uuid.uuid4())
    job = client.call("/api/jobs", spec, key)["id"]
    assert client.call("/api/jobs", spec, key)["id"] == job
    wait_for(client, job)
    task = store.tasks(job)[0]
    app.send_task("platform_eval.evaluate", args=[task["id"]], task_id=task["id"])
    time.sleep(2)
    assert len(store.tasks(job)[0]["attempts"]) == 1
    assert client.call(f"/api/jobs/{job}/results")["complete"]
    assert Store(settings).job(job)["state"] == "COMPLETED"
    print("PASS API -> Redis -> Celery -> child -> persistent result; duplicate delivery ignored", flush=True)

    # Force an input identity error, then fix only the engineering fixture identity.
    valid = freeze(settings, "fixture")
    retry_job = store.submit(spec, "intentionally-invalid-fixture-identity")
    until = time.monotonic() + 30
    while time.monotonic() < until:
        retry_task = store.tasks(retry_job)[0]
        if retry_task["state"] == "RETRYING":
            break
        time.sleep(0.1)
    else:
        raise AssertionError(store.tasks(retry_job))
    with store.connection(True) as db:
        db.execute("UPDATE jobs SET fingerprint=? WHERE id=?", (valid, retry_job))
    wait_for(client, retry_job)
    assert len(store.tasks(retry_job)[0]["attempts"]) >= 2
    print("PASS actual failed child -> persisted retry -> successful re-execution", flush=True)

    crash_job = store.submit(spec, valid)
    crash_task = store.tasks(crash_job)[0]
    owner = store.claim(crash_task["id"], "simulated-crashed-worker")
    assert owner
    with store.connection(True) as db:
        db.execute("UPDATE tasks SET lease=? WHERE id=?", (time.time() - 1, crash_task["id"]))
    wait_for(client, crash_job)
    assert store.tasks(crash_job)[0]["attempts"][0]["error"] == "Worker lease expired"
    assert not store.finish(crash_task["id"], owner["token"], result={})
    print("PASS stale lease recovered by live coordinator; stale owner fenced", flush=True)

    if args.real:
        real_spec = {
            "mode": "smoke",
            "configurations": [
                {"chunker": c, "noise": "clean"} for c in ("fixed", "recursive", "semantic", "structure")
            ],
        }
        real_job = client.call("/api/jobs", real_spec)["id"]
        wait_for(client, real_job, timeout=300)
        results = client.call(f"/api/jobs/{real_job}/results")["results"]
        golden = json.loads(
            (Path(__file__).parents[1] / "tests/fixtures/sequential_reference.json").read_text()
        )
        for result in results:
            for name, expected in golden["configurations"][result["chunker"]].items():
                assert result[name] == expected, (result["chunker"], name)
        print(
            "PASS real MiniLM + four original chunkers + FAISS through Redis/Celery; frozen rankings/metrics match",
            flush=True,
        )
    print(
        json.dumps(
            {
                "status": "passed",
                "scope": "engineering integration and small real-RAG diagnostic; not an OHRBench benchmark",
            }
        )
    )


if __name__ == "__main__":
    main()
