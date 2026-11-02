"""Single-process local coordinator API; OpenAPI is available at /docs."""

import functools
import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, Response
from redis import Redis

from .config import Settings
from .contracts import JobRequest, JobView, ResultsView, TaskView
from .coordinator import serve
from .db import CapacityError, ConflictError, Store
from .inputs import freeze
from .metrics import Metrics


def create_app(settings=None, dispatch=True):
    settings = settings or Settings()
    store = Store(settings)
    broker = Redis.from_url(settings.broker, socket_timeout=2, socket_connect_timeout=2)
    metrics = Metrics(store, broker)
    logger = logging.getLogger(__name__)

    @functools.lru_cache(maxsize=2)
    def input_identity(mode):
        return freeze(settings, mode)

    @asynccontextmanager
    async def lifespan(app):
        stop = threading.Event()
        thread = None
        if dispatch:
            thread = threading.Thread(target=serve, args=(stop, settings), daemon=True)
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=5)

    api = FastAPI(title="Distributed RAG Evaluation", version="1.0", lifespan=lifespan)
    api.state.store = store
    api.state.metrics = metrics

    @api.middleware("http")
    async def observe(request, call_next):
        started = time.monotonic()
        response = await call_next(request)
        route = request.scope.get("route")
        # Unknown arbitrary paths share a label; IDs never become labels.
        label = route.path if route else "unmatched"
        metrics.requests.labels(request.method, label).observe(time.monotonic() - started)
        if response.status_code >= 500:
            metrics.errors.inc()
        return response

    def require_job(job_id):
        job = store.job(job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return job

    @api.post("/api/jobs", status_code=202, response_model=JobView)
    def submit(request: JobRequest, idempotency_key: Annotated[str | None, Header(max_length=128)] = None):
        if request.mode in ("fixture", "smoke") and not settings.allow_fixture:
            raise HTTPException(403, "Engineering fixtures disabled")
        try:
            fingerprint = input_identity(request.mode)
            job_id = store.submit(request.model_dump(), fingerprint, idempotency_key)
        except CapacityError as exc:
            raise HTTPException(429, str(exc), headers={"Retry-After": "30"}) from exc
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (OSError, ValueError) as exc:
            logger.exception("Input preflight failed")
            raise HTTPException(503, "Research inputs unavailable; see coordinator logs") from exc
        return store.job(job_id)

    @api.get("/api/jobs", response_model=list[JobView])
    def list_jobs(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        return store.jobs(limit, offset)

    @api.get("/api/jobs/{job_id}", response_model=JobView)
    def get_job(job_id: str):
        return require_job(job_id)

    @api.get("/api/jobs/{job_id}/tasks", response_model=list[TaskView])
    def get_tasks(job_id: str):
        require_job(job_id)
        return store.tasks(job_id)

    @api.get("/api/jobs/{job_id}/results", response_model=ResultsView)
    def get_results(job_id: str):
        job = require_job(job_id)
        tasks = store.tasks(job_id)
        # Partial results are explicit, never passed off as a complete experiment.
        return {
            "job_id": job_id,
            "complete": job["state"] == "COMPLETED",
            "state": job["state"],
            "results": [t["result"] for t in tasks if t["state"] == "COMPLETED"],
        }

    @api.post("/api/jobs/{job_id}/cancel", response_model=JobView)
    def cancel(job_id: str):
        require_job(job_id)
        if not store.cancel(job_id):
            raise HTTPException(409, "Job already terminal")
        return store.job(job_id)

    @api.get("/health")
    def health():
        return {"status": "alive"}

    @api.get("/ready")
    def ready():
        try:
            with store.connection() as db:
                db.execute("SELECT 1").fetchone()
            broker.ping()
        except Exception as exc:
            raise HTTPException(503, "Metadata storage or broker unavailable") from exc
        return {"status": "ready", "scope": "metadata-and-broker; research inputs checked on submission"}

    @api.get("/metrics", include_in_schema=False)
    def prometheus():
        return Response(metrics.render(), media_type="text/plain; version=0.0.4")

    return api


app = create_app()
