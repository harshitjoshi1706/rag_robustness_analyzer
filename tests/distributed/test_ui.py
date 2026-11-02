import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class DistributedUITests(unittest.TestCase):
    def test_coordinator_unavailable_is_recoverable(self):
        with patch("services.platform_client.PlatformClient.call", side_effect=ConnectionError("offline")):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app.py")).run()
            app.switch_page("pages/4_Distributed_Evaluation.py").run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Coordinator unavailable" in error.value for error in app.error))

    def test_submit_and_display_running_task(self):
        job = {
            "id": "job-1",
            "created": 1,
            "state": "RUNNING",
            "completed": 0,
            "total": 1,
            "spec": {"mode": "research"},
            "fingerprint": "hash",
        }
        task = {
            "chunker": "fixed",
            "noise": "clean",
            "state": "RUNNING",
            "attempt": 2,
            "worker": "worker-1",
            "error": None,
            "attempts": [],
            "result": None,
        }

        def call(path, body=None, key=None):
            if path == "/api/jobs":
                self.assertTrue(key)
                return job
            if path.endswith("/tasks"):
                return [task]
            if path.startswith("/api/jobs?"):
                return [job]
            return job

        with patch("services.platform_client.PlatformClient.call", side_effect=call):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app.py")).run()
            app.switch_page("pages/4_Distributed_Evaluation.py").run()
            self.assertFalse(app.exception)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Job accepted" in success.value for success in app.success))
            self.assertTrue(app.dataframe)
