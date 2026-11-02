"""Container-local presence probe; does not ping every Celery worker."""

import socket
import sys
import time

from .config import Settings
from .db import Store

store = Store(Settings())
with store.connection() as db:
    row = db.execute("SELECT seen FROM workers WHERE id=?", (f"worker@{socket.gethostname()}",)).fetchone()
sys.exit(0 if row and row[0] > time.time() - 45 else 1)
