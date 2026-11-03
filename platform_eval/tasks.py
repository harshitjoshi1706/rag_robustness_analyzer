"""Fenced task claims and supervised research subprocesses."""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .celery_app import app
from .config import Settings
from .db import Store
from .research import validate_result
from .storage import atomic_json, valid_manifest

logger = logging.getLogger(__name__)


def run_task(task_id, worker):
    settings = Settings()
    store = Store(settings)
    task = store.claim(task_id, worker)
    if task is None:
        return {"delivery": "ignored"}
    job = store.job(task["job_id"])
    output = settings.storage / "attempts" / task_id / task["token"]
    output.mkdir(parents=True, exist_ok=True)
    request_file = output / "request.json"
    atomic_json(
        request_file,
        {
            "task": {k: task[k] for k in ("chunker", "noise")},
            "fingerprint": job["fingerprint"],
            "output": str(output),
            "mode": job["spec"]["mode"],
            "cache_namespace": job["spec"].get("cache_namespace", "shared"),
        },
    )
    started = time.monotonic()
    peak_rss = cpu_seconds = cpu_percent = rss = 0.0
    child = None
    try:
        with (output / "execution.log").open("w") as log:
            child = subprocess.Popen(
                [sys.executable, "-m", "platform_eval.child", str(request_file)],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env={
                    **os.environ,
                    "OMP_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                    "TOKENIZERS_PARALLELISM": "false",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "RAG_SUPERVISOR_PID": str(os.getpid()),
                    "NLTK_DATA": str(Path(__file__).parent / "data"),
                },
            )
            process = psutil.Process(child.pid)
            while child.poll() is None:
                progress = {"stage": "starting"}
                try:
                    progress = json.loads((output / "progress.json").read_text())
                except (OSError, ValueError):
                    pass
                progress["rss_bytes_sampled"] = int(rss)
                progress["cpu_percent_sampled"] = cpu_percent
                progress["published_query_batches"] = len(list((output / "parts").glob("batch_*.csv")))
                if not store.heartbeat(worker, task_id, task["token"], progress):
                    raise RuntimeError("Task cancelled or fenced by recovery")
                if time.monotonic() - started > settings.task_timeout:
                    raise TimeoutError("Evaluation exceeded configured wall-clock limit")
                try:
                    rss = process.memory_info().rss
                    peak_rss = max(peak_rss, rss)
                    cpu_percent = process.cpu_percent(None)
                    cpu = process.cpu_times()
                    cpu_seconds = max(cpu_seconds, cpu.user + cpu.system)
                except psutil.NoSuchProcess:
                    pass
                time.sleep(min(1, settings.lease_seconds / 3))
            if child.returncode:
                # Bound DB error size; full diagnostic stays in attempt log.
                with (output / "execution.log").open("rb") as stream:
                    stream.seek(max(0, (output / "execution.log").stat().st_size - 4000))
                    tail = stream.read().decode(errors="replace")
                raise RuntimeError(f"Research child exited {child.returncode}: {tail}")
        result = json.loads((output / "result.json").read_text())
        names = json.loads((output / "checksums.json").read_text())["files"]
        if "result.json" not in names or not valid_manifest(output, job["fingerprint"], names):
            raise ValueError("Attempt artifacts failed integrity validation")
        validate_result(
            result,
            task,
            job["fingerprint"],
            {"research": 8456, "smoke": 4, "fixture": 2}[job["spec"]["mode"]],
        )
        result["execution"] = {
            "duration_seconds": time.monotonic() - started,
            "peak_rss_bytes_sampled": int(peak_rss),
            "cpu_seconds_sampled": cpu_seconds,
            "worker": worker,
            "attempt": task["attempt"],
            "artifact_directory": str(output.relative_to(settings.storage)),
        }
        committed = store.finish(task_id, task["token"], result=result)
        logger.info(
            json.dumps(
                {
                    "event": "task_finished",
                    "task": task_id,
                    "attempt": task["attempt"],
                    "committed": committed,
                }
            )
        )
        return {"committed": committed}
    except Exception as exc:
        store.finish(task_id, task["token"], error=f"{type(exc).__name__}: {exc}"[:5000])
        logger.exception(json.dumps({"event": "task_failed", "task": task_id, "attempt": task["attempt"]}))
        return {"error": str(exc)[:5000]}
    finally:
        if child and child.poll() is None:
            # The process has its own group. Terminate the model process on fencing.
            import signal

            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


@app.task(name="platform_eval.evaluate")
def evaluate(task_id):
    from celery import current_task

    return run_task(task_id, current_task.request.hostname or "unknown")
