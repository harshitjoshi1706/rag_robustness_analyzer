"""Redis is delivery only; SQLite remains authoritative."""

import logging
import threading

from celery import Celery, bootsteps

from .config import Settings
from .db import Store

settings = Settings()
app = Celery("rag_evaluation", broker=settings.broker, include=["platform_eval.tasks"])
app.conf.update(
    task_default_queue="evaluation",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=1,
    worker_max_tasks_per_child=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": settings.task_timeout + 300},
    task_serializer="json",
    accept_content=["json"],
    task_publish_retry=False,
    broker_connection_timeout=3,
    worker_cancel_long_running_tasks_on_connection_loss=True,
)


class Presence(bootsteps.StartStopStep):
    """Report idle workers as well as workers executing tasks."""

    def start(self, worker):
        self.stop_event = threading.Event()
        self.worker_id = str(worker.hostname)

        def loop():
            store = Store(settings)
            while not self.stop_event.is_set():
                try:
                    store.heartbeat(self.worker_id)
                except Exception:
                    logging.getLogger(__name__).exception("Worker presence heartbeat failed")
                self.stop_event.wait(15)

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def stop(self, worker):
        self.stop_event.set()
        self.thread.join(timeout=2)


app.steps["worker"].add(Presence)
