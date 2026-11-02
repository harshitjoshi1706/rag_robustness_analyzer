"""Restart-safe dispatch loop; bounded duplicate publication, no ML imports."""

import logging
import threading

from redis import Redis

from .celery_app import app
from .config import Settings
from .db import Store

logger = logging.getLogger(__name__)


def tick(settings, store, broker=None, publish=None):
    store.recover()
    broker = broker or Redis.from_url(settings.broker, socket_timeout=3, socket_connect_timeout=3)
    # Redis transport may create priority queues; priority is never enabled here.
    depth = broker.llen("evaluation")
    if depth >= settings.max_pending:
        return
    publish = publish or (
        lambda task_id: app.send_task("platform_eval.evaluate", args=[task_id], task_id=task_id)
    )
    for task_id in store.dispatch_due(limit=min(16, settings.max_pending - depth)):
        publish(task_id)


def serve(stop, settings=None):
    settings = settings or Settings()
    store = Store(settings)
    while not stop.is_set():
        try:
            tick(settings, store)
        except Exception:
            logger.exception('{"event":"dispatch_or_recovery_error"}')
        stop.wait(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve(threading.Event())
