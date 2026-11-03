import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from platform_eval.config import Settings
from platform_eval.contracts import JobRequest
from platform_eval.db import CapacityError, ConflictError, Store
from platform_eval.storage import atomic_json, publish_manifest, valid_manifest

SPEC = {"mode": "fixture", "configurations": [{"chunker": "fixed", "noise": "clean"}]}


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = replace(Settings(), storage=Path(self.temp.name), allow_fixture=True)
        self.store = Store(self.settings)

    def tearDown(self):
        self.temp.cleanup()

    def submit(self):
        job = self.store.submit(SPEC, "fingerprint")
        return job, self.store.tasks(job)[0]["id"]

    def test_validation_and_identity(self):
        with self.assertRaises(ValueError):
            JobRequest(configurations=[{"chunker": "new", "noise": "clean"}])
        with self.assertRaises(ValueError):
            JobRequest(configurations=SPEC["configurations"] * 2)
        first = self.store.submit(SPEC, "fingerprint", "key")
        self.assertEqual(first, self.store.submit(SPEC, "fingerprint", "key"))
        with self.assertRaises(ConflictError):
            self.store.submit(SPEC, "different", "key")

    def test_concurrent_duplicate_claims_and_single_commit(self):
        job, task_id = self.submit()
        with ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(lambda i: self.store.claim(task_id, f"worker-{i}"), range(8)))
        owners = [c for c in claims if c]
        self.assertEqual(len(owners), 1)
        token = owners[0]["token"]
        self.assertTrue(self.store.finish(task_id, token, result={"value": 1}))
        self.assertFalse(self.store.finish(task_id, token, result={"value": 2}))
        self.assertEqual(self.store.tasks(job)[0]["result"], {"value": 1})
        self.assertEqual(self.store.job(job)["state"], "COMPLETED")
        self.assertIsNone(self.store.claim(task_id, "duplicate"))

    def test_crash_recovery_fences_previous_owner_and_bounds_retries(self):
        job, task_id = self.submit()
        for attempt in range(1, 4):
            claimed = self.store.claim(task_id, "worker")
            self.assertEqual(claimed["attempt"], attempt)
            with self.store.connection(True) as db:
                db.execute("UPDATE tasks SET lease=? WHERE id=?", (time.time() - 1, task_id))
            # Coordinator restarts with only on-disk state.
            restarted = Store(self.settings)
            self.assertEqual(restarted.recover(), 1)
            self.assertFalse(restarted.finish(task_id, claimed["token"], result={}))
            with self.store.connection(True) as db:
                db.execute("UPDATE tasks SET due=0 WHERE id=?", (task_id,))
        self.assertEqual(self.store.job(job)["state"], "FAILED")
        self.assertIsNone(self.store.claim(task_id, "fourth-attempt"))
        self.assertEqual(len(self.store.tasks(job)[0]["attempts"]), 3)

    def test_cancellation_fences_running_and_unscheduled_tasks(self):
        job, task_id = self.submit()
        claim = self.store.claim(task_id, "worker")
        self.assertTrue(self.store.cancel(job))
        self.assertFalse(self.store.heartbeat("worker", task_id, claim["token"]))
        self.assertFalse(self.store.finish(task_id, claim["token"], result={}))
        self.assertEqual(self.store.job(job)["state"], "CANCELLED")

    def test_durable_dispatch_after_ambiguous_publish(self):
        _, task_id = self.submit()
        self.assertEqual(self.store.dispatch_due(), [task_id])
        self.assertEqual(self.store.dispatch_due(), [])
        with self.store.connection(True) as db:
            db.execute("UPDATE tasks SET dispatched=0 WHERE id=?", (task_id,))
        self.assertEqual(Store(self.settings).dispatch_due(), [task_id])

    def test_admission_bound_is_transactional(self):
        limited = Store(replace(self.settings, max_pending=1))
        limited.submit(SPEC, "fingerprint")
        with self.assertRaises(CapacityError):
            limited.submit(SPEC, "fingerprint")
        self.assertEqual(len(limited.jobs()), 1)

    def test_incomplete_aggregation_cannot_complete_job(self):
        spec = {
            "mode": "fixture",
            "configurations": SPEC["configurations"] + [{"chunker": "recursive", "noise": "clean"}],
        }
        job = self.store.submit(spec, "fingerprint")
        task = self.store.claim(self.store.tasks(job)[0]["id"], "worker")
        self.store.finish(task["id"], task["token"], result={})
        self.assertEqual(self.store.job(job)["state"], "RUNNING")
        self.assertEqual(self.store.job(job)["completed"], 1)

    def test_partial_writes_and_corruption_are_not_cache_hits(self):
        root = Path(self.temp.name) / "artifacts"
        atomic_json(root / "index.json", {"valid": True})
        self.assertFalse(valid_manifest(root, "hash", ["index.json"]))
        publish_manifest(root, ["index.json"], "hash")
        self.assertTrue(valid_manifest(root, "hash", ["index.json"]))
        (root / "index.json").write_text("partial")
        self.assertFalse(valid_manifest(root, "hash", ["index.json"]))
        self.assertFalse(valid_manifest(root, "other", ["index.json"]))
        self.assertFalse(list(root.glob("*.tmp")))

    def test_retry_backoff_and_failure_preserve_diagnostic(self):
        job, task_id = self.submit()
        task = self.store.claim(task_id, "worker")
        self.store.finish(task_id, task["token"], error="failed to load input")
        updated = self.store.tasks(job)[0]
        self.assertEqual(updated["state"], "RETRYING")
        self.assertGreater(updated["due"], time.time())
        self.assertIsNone(self.store.claim(task_id, "worker"))
        self.assertEqual(json.loads(json.dumps(updated))["error"], "failed to load input")
