"""Global measurements come from persistent metadata, across worker processes."""

import json
import time

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from .db import TERMINAL


class Metrics:
    def __init__(self, store, broker):
        self.store, self.broker = store, broker
        self.registry = CollectorRegistry()
        self.requests = Histogram(
            "rag_api_request_seconds", "API latency", ["method", "route"], registry=self.registry
        )
        self.errors = Counter("rag_api_errors", "API responses >=500", registry=self.registry)

    def render(self):
        registry = CollectorRegistry()
        with self.store.connection() as db:
            states = dict(db.execute("SELECT state,count(*) FROM tasks GROUP BY state").fetchall())
            tasks = Gauge("rag_tasks", "Logical tasks by state", ["state"], registry=registry)
            for state in (*TERMINAL, "RUNNING", "PENDING", "RETRYING"):
                tasks.labels(state).set(states.get(state, 0))
            attempts = Counter("rag_attempts", "Finished attempt count", ["state"], registry=registry)
            for state, count in db.execute(
                "SELECT state,count(*) FROM attempts WHERE finished IS NOT NULL GROUP BY state"
            ):
                attempts.labels(state).inc(count)
            retry = Counter("rag_retries", "Retry attempts started", registry=registry)
            retry.inc(db.execute("SELECT count(*) FROM attempts WHERE number>1").fetchone()[0])
            durations = Histogram(
                "rag_task_duration_seconds",
                "Finished attempt duration",
                buckets=(1, 10, 60, 300, 900, 3600, 21600),
                registry=registry,
            )
            for row in db.execute("SELECT finished-started FROM attempts WHERE finished IS NOT NULL"):
                durations.observe(row[0])
            jobs = Histogram(
                "rag_job_duration_seconds",
                "Terminal job duration",
                buckets=(1, 10, 60, 300, 900, 3600, 21600),
                registry=registry,
            )
            for row in db.execute("SELECT finished-created FROM jobs WHERE finished IS NOT NULL"):
                jobs.observe(row[0])
            resources = [
                json.loads(row[0]) for row in db.execute("SELECT progress FROM tasks WHERE state='RUNNING'")
            ]
            memory = Gauge(
                "rag_active_evaluation_rss_bytes",
                "Sum of sampled active evaluation child RSS",
                registry=registry,
            )
            memory.set(sum(p.get("rss_bytes_sampled", 0) for p in resources))
            cpu = Gauge(
                "rag_active_evaluation_cpu_cores",
                "Sum of sampled active evaluation CPU percent / 100",
                registry=registry,
            )
            cpu.set(sum(p.get("cpu_percent_sampled", 0) for p in resources) / 100)
            workers = Gauge("rag_workers_available", "Workers seen within 45 seconds", registry=registry)
            workers.set(
                db.execute("SELECT count(*) FROM workers WHERE seen>?", (time.time() - 45,)).fetchone()[0]
            )
        queue = Gauge(
            "rag_queue_depth", "Redis delivery queue length; duplicates included", registry=registry
        )
        available = Gauge("rag_broker_available", "Whether Redis metrics probe succeeded", registry=registry)
        try:
            queue.set(self.broker.llen("evaluation"))
            available.set(1)
        except Exception:
            # Do not report zero queue depth on a failed probe.
            queue.set(float("nan"))
            available.set(0)
        return generate_latest(registry) + generate_latest(self.registry)
