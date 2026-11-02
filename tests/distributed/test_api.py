import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from platform_eval.api import create_app
from platform_eval.config import Settings

SPEC = {"mode": "fixture", "configurations": [{"chunker": "fixed", "noise": "clean"}]}


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = replace(Settings(), storage=Path(self.temp.name), allow_fixture=True)
        self.app = create_app(self.settings, dispatch=False)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_submit_poll_results_cancel_and_openapi(self):
        response = self.client.post("/api/jobs", json=SPEC, headers={"Idempotency-Key": "same"})
        self.assertEqual(response.status_code, 202)
        job = response.json()
        self.assertEqual(
            self.client.post("/api/jobs", json=SPEC, headers={"Idempotency-Key": "same"}).json()["id"],
            job["id"],
        )
        self.assertEqual(self.client.get("/api/jobs").json()[0]["id"], job["id"])
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}").json()["total"], 1)
        self.assertFalse(self.client.get(f"/api/jobs/{job['id']}/results").json()["complete"])
        task = self.client.get(f"/api/jobs/{job['id']}/tasks").json()[0]
        self.assertEqual(task["state"], "PENDING")
        self.assertEqual(self.client.post(f"/api/jobs/{job['id']}/cancel").json()["state"], "CANCELLED")
        self.assertEqual(self.client.post(f"/api/jobs/{job['id']}/cancel").status_code, 409)
        self.assertIn("/api/jobs", self.client.get("/openapi.json").json()["paths"])

    def test_errors_health_and_readiness(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/api/jobs/missing").status_code, 404)
        self.assertEqual(self.client.post("/api/jobs", json={"configurations": []}).status_code, 422)
        self.assertEqual(self.client.get("/api/jobs?limit=1000").status_code, 422)
        with patch("redis.Redis.ping", side_effect=ConnectionError):
            self.assertEqual(self.client.get("/ready").status_code, 503)
        with patch("redis.Redis.ping", return_value=True):
            self.assertEqual(self.client.get("/ready").status_code, 200)
        disabled = TestClient(create_app(replace(self.settings, allow_fixture=False), dispatch=False))
        self.assertEqual(disabled.post("/api/jobs", json=SPEC).status_code, 403)

    def test_metrics_are_global_from_db_and_have_bounded_labels(self):
        job = self.client.post("/api/jobs", json=SPEC).json()
        store = self.app.state.store
        task = store.claim(store.tasks(job["id"])[0]["id"], "worker-one")
        store.finish(task["id"], task["token"], result={})
        store.heartbeat("worker-one")
        with patch("redis.Redis.llen", return_value=0):
            text = self.client.get("/metrics").text
        self.assertIn('rag_tasks{state="COMPLETED"} 1.0', text)
        self.assertIn('rag_attempts_total{state="COMPLETED"} 1.0', text)
        self.assertIn("rag_workers_available 1.0", text)
        self.assertNotIn(job["id"], text)
