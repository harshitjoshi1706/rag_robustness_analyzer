"""Single-host SQLite authority. Every ownership change uses a fenced transaction."""

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager

from .contracts import identity

TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, request_key TEXT UNIQUE, request_hash TEXT NOT NULL,
 spec TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL,
 created REAL NOT NULL, finished REAL
);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
 chunker TEXT NOT NULL, noise TEXT NOT NULL, state TEXT NOT NULL,
 attempt INTEGER NOT NULL DEFAULT 0, token TEXT, worker TEXT, lease REAL,
 due REAL NOT NULL, dispatched REAL NOT NULL DEFAULT 0,
 result TEXT, error TEXT, UNIQUE(job_id,chunker,noise)
);
CREATE INDEX IF NOT EXISTS tasks_due ON tasks(state,due,dispatched);
CREATE TABLE IF NOT EXISTS attempts (
 task_id TEXT NOT NULL REFERENCES tasks(id), number INTEGER NOT NULL,
 token TEXT NOT NULL, worker TEXT NOT NULL, started REAL NOT NULL,
 finished REAL, state TEXT NOT NULL, error TEXT,
 PRIMARY KEY(task_id,number)
);
CREATE TABLE IF NOT EXISTS workers (id TEXT PRIMARY KEY, seen REAL NOT NULL);
"""


class CapacityError(Exception):
    pass


class ConflictError(Exception):
    pass


class Store:
    def __init__(self, settings):
        self.settings = settings
        settings.storage.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(settings.database, timeout=30, isolation_level=None) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.settings.database, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=FULL")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def submit(self, spec, fingerprint, key=None):
        canonical = {
            **spec,
            "configurations": sorted(spec["configurations"], key=lambda c: (c["chunker"], c["noise"])),
        }
        request_hash = identity({"spec": canonical, "fingerprint": fingerprint})
        now = time.time()
        with self.connection(True) as db:
            if key:
                existing = db.execute("SELECT * FROM jobs WHERE request_key=?", (key,)).fetchone()
                if existing:
                    if existing["request_hash"] != request_hash:
                        raise ConflictError("Idempotency key belongs to a different request")
                    return existing["id"]
            pending = db.execute(
                "SELECT count(*) FROM tasks WHERE state NOT IN (?,?,?)", TERMINAL
            ).fetchone()[0]
            if pending + len(canonical["configurations"]) > self.settings.max_pending:
                raise CapacityError("Outstanding task limit reached; retry later")
            job_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,NULL)",
                (job_id, key, request_hash, json.dumps(canonical), fingerprint, "PENDING", now),
            )
            for config in canonical["configurations"]:
                task_id = str(uuid.uuid5(uuid.UUID(job_id), f"{config['chunker']}/{config['noise']}"))
                db.execute(
                    "INSERT INTO tasks (id,job_id,chunker,noise,state,due) VALUES (?,?,?,?,?,?)",
                    (task_id, job_id, config["chunker"], config["noise"], "PENDING", now),
                )
        return job_id

    def job(self, job_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["spec"] = json.loads(result["spec"])
            counts = dict(
                db.execute(
                    "SELECT state,count(*) FROM tasks WHERE job_id=? GROUP BY state", (job_id,)
                ).fetchall()
            )
            result.update(counts=counts, completed=counts.get("COMPLETED", 0), total=sum(counts.values()))
            return result

    def jobs(self, limit=50, offset=0):
        with self.connection() as db:
            ids = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM jobs ORDER BY created DESC LIMIT ? OFFSET ?", (limit, offset)
                )
            ]
        return [self.job(job_id) for job_id in ids]

    def tasks(self, job_id):
        with self.connection() as db:
            tasks = [
                dict(row)
                for row in db.execute("SELECT * FROM tasks WHERE job_id=? ORDER BY chunker,noise", (job_id,))
            ]
            for task in tasks:
                task["result"] = json.loads(task["result"]) if task["result"] else None
                task["attempts"] = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM attempts WHERE task_id=? ORDER BY number", (task["id"],)
                    )
                ]
        return tasks

    @staticmethod
    def refresh_job(db, job_id, now):
        states = [r[0] for r in db.execute("SELECT state FROM tasks WHERE job_id=?", (job_id,))]
        current = db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
        if current == "CANCELLED":
            return
        if all(s == "COMPLETED" for s in states):
            state = "COMPLETED"
        elif all(s in TERMINAL for s in states):
            state = "FAILED"
        elif any(s != "PENDING" for s in states):
            state = "RUNNING"
        else:
            state = "PENDING"
        db.execute(
            "UPDATE jobs SET state=?,finished=? WHERE id=?",
            (state, now if state in TERMINAL else None, job_id),
        )

    def dispatch_due(self, limit=16):
        now = time.time()
        with self.connection(True) as db:
            rows = db.execute(
                "SELECT id FROM tasks WHERE state IN ('PENDING','RETRYING') AND due<=? AND dispatched<=? LIMIT ?",
                (now, now - 30, limit),
            ).fetchall()
            for row in rows:
                db.execute("UPDATE tasks SET dispatched=? WHERE id=?", (now, row[0]))
        return [row[0] for row in rows]

    def claim(self, task_id, worker):
        now = time.time()
        with self.connection(True) as db:
            task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task or task["state"] not in ("PENDING", "RETRYING") or task["due"] > now:
                return None
            token = uuid.uuid4().hex
            number = task["attempt"] + 1
            db.execute(
                "UPDATE tasks SET state='RUNNING',attempt=?,token=?,worker=?,lease=?,error=NULL WHERE id=?",
                (number, token, worker, now + self.settings.lease_seconds, task_id),
            )
            db.execute(
                "INSERT INTO attempts VALUES (?,?,?,?,?,NULL,'RUNNING',NULL)",
                (task_id, number, token, worker, now),
            )
            db.execute("UPDATE jobs SET state='RUNNING' WHERE id=?", (task["job_id"],))
            return {**dict(task), "attempt": number, "token": token, "worker": worker}

    def heartbeat(self, worker, task_id=None, token=None):
        now = time.time()
        with self.connection(True) as db:
            db.execute(
                "INSERT INTO workers VALUES (?,?) ON CONFLICT(id) DO UPDATE SET seen=excluded.seen",
                (worker, now),
            )
            if task_id:
                return (
                    db.execute(
                        "UPDATE tasks SET lease=? WHERE id=? AND token=? AND state='RUNNING'",
                        (now + self.settings.lease_seconds, task_id, token),
                    ).rowcount
                    == 1
                )
        return True

    def finish(self, task_id, token, result=None, error=None):
        now = time.time()
        with self.connection(True) as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE id=? AND token=? AND state='RUNNING' AND lease>?",
                (task_id, token, now),
            ).fetchone()
            if not row:
                return False
            self._finish(db, row, now, result, error)
        return True

    def _finish(self, db, row, now, result, error):
        if error:
            state = "FAILED" if row["attempt"] >= self.settings.max_attempts else "RETRYING"
        else:
            state = "COMPLETED"
        db.execute(
            "UPDATE tasks SET state=?,result=?,error=?,lease=NULL,token=NULL,due=?,dispatched=0 WHERE id=?",
            (
                state,
                json.dumps(result, allow_nan=False) if result is not None else None,
                error,
                now + min(300, 2 ** row["attempt"]),
                row["id"],
            ),
        )
        db.execute(
            "UPDATE attempts SET state=?,finished=?,error=? WHERE task_id=? AND number=?",
            ("FAILED" if error else "COMPLETED", now, error, row["id"], row["attempt"]),
        )
        self.refresh_job(db, row["job_id"], now)

    def recover(self):
        now = time.time()
        with self.connection(True) as db:
            stale = db.execute("SELECT * FROM tasks WHERE state='RUNNING' AND lease<?", (now,)).fetchall()
            for row in stale:
                self._finish(db, row, now, None, "Worker lease expired")
        return len(stale)

    def cancel(self, job_id):
        now = time.time()
        with self.connection(True) as db:
            row = db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row[0] in TERMINAL:
                return False
            db.execute("UPDATE jobs SET state='CANCELLED',finished=? WHERE id=?", (now, job_id))
            db.execute(
                "UPDATE attempts SET state='CANCELLED',finished=? WHERE task_id IN (SELECT id FROM tasks WHERE job_id=?) AND state='RUNNING'",
                (now, job_id),
            )
            db.execute(
                "UPDATE tasks SET state='CANCELLED',token=NULL,lease=NULL WHERE job_id=? AND state NOT IN (?,?,?)",
                (job_id, *TERMINAL),
            )
        return True
