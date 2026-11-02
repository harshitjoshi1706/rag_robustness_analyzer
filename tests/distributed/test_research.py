import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platform_eval.config import Settings
from platform_eval.contracts import CHUNKERS
from platform_eval.db import Store
from platform_eval.inputs import freeze
from platform_eval.research import validate_result
from platform_eval.tasks import run_task


class ResultValidationTests(unittest.TestCase):
    def test_reject_mismatched_or_nonfinite_metrics(self):
        task = {"chunker": "fixed", "noise": "clean"}
        result = {
            "fingerprint": "abc",
            **task,
            "question_count": 2,
            "hit_at_1": 0.5,
            "hit_at_5": 1.0,
            "mrr_at_100": 0.75,
        }
        self.assertEqual(validate_result(result, task, "abc", 2), result)
        for change in (
            {"question_count": 1},
            {"fingerprint": "other"},
            {"mrr_at_100": float("nan")},
            {"hit_at_1": 1.0, "hit_at_5": 0.5},
        ):
            with self.assertRaises(ValueError):
                validate_result({**result, **change}, task, "abc", 2)

    def test_actual_child_commits_fixture_and_ignores_duplicate(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "RAG_STORAGE": directory,
                    "RAG_ALLOW_FIXTURE": "1",
                },
            ),
        ):
            settings = Settings()
            store = Store(settings)
            spec = {"mode": "fixture", "configurations": [{"chunker": "fixed", "noise": "clean"}]}
            job = store.submit(spec, freeze(settings, "fixture"))
            task = store.tasks(job)[0]
            self.assertTrue(run_task(task["id"], "test-worker")["committed"])
            self.assertEqual(run_task(task["id"], "duplicate"), {"delivery": "ignored"})
            self.assertEqual(store.job(job)["state"], "COMPLETED")


@unittest.skipUnless(os.getenv("RUN_REAL_RAG_TESTS") == "1", "Opt-in real MiniLM/FAISS regression")
class RealResearchRegressionTests(unittest.TestCase):
    def test_cold_and_warm_child_outputs_match_frozen_original_helpers(self):
        golden = json.loads((Path(__file__).parents[1] / "fixtures/sequential_reference.json").read_text())
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "RAG_STORAGE": directory,
                    "RAG_ALLOW_FIXTURE": "1",
                    "RAG_MODEL_PATH": str(Settings().model_path),
                    "RAG_RESEARCH_ROOT": str(Settings().research),
                },
            ),
        ):
            settings = Settings()
            store = Store(settings)
            fingerprint = freeze(settings, "smoke")
            for warm in (False, True):
                spec = {
                    "mode": "smoke",
                    "configurations": [{"chunker": c, "noise": "clean"} for c in CHUNKERS],
                }
                job = store.submit(spec, fingerprint)
                for task in store.tasks(job):
                    self.assertTrue(
                        run_task(task["id"], "regression-worker").get("committed"), store.tasks(job)
                    )
                    result = next(t["result"] for t in store.tasks(job) if t["id"] == task["id"])
                    self.assertEqual(result["cache_hit"], warm)
                    for name, expected in golden["configurations"][task["chunker"]].items():
                        # Counts, metrics and per-question ranking identities are exact.
                        self.assertEqual(result[name], expected, (task["chunker"], name))
                self.assertEqual(store.job(job)["state"], "COMPLETED")
