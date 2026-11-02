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

    def test_original_runner_contract_with_full_count_deterministic_fixture(self):
        """Exercise the real run_configuration/CSV path without corpus inference.

        QAs/vectors are explicitly test fixtures, not official research measurements.
        Their frozen contract sizes exercise batch boundaries, schema and aggregation.
        """
        from unittest.mock import patch

        import numpy as np

        from platform_eval.research import execute, import_runner
        from platform_eval.storage import atomic_json, publish_manifest

        previous_cwd = Path.cwd()
        try:
            with (
                tempfile.TemporaryDirectory() as directory,
                patch.dict(
                    os.environ,
                    {
                        "RAG_STORAGE": directory,
                    },
                ),
            ):
                settings = Settings()
                runner = import_runner(settings)
                qas = [
                    {
                        "query_id": f"test-{i:05}",
                        "question": "test query",
                        "doc_name": "test-document",
                        "domain": "debug",
                        "evidence_pages": [1],
                        "context_verified": i < 5277,
                    }
                    for i in range(8456)
                ]
                runner.read_qas = lambda: (qas, [])
                manifest = {"scope": "test-only-input-snapshot"}
                from platform_eval.contracts import identity

                fingerprint = identity(manifest)
                cache = settings.storage / "cache/shared" / fingerprint
                queries = cache / "queries"
                queries.mkdir(parents=True)
                vectors = np.zeros((8456, 384), dtype=np.float32)
                vectors[:, 0] = 1
                np.save(queries / "official_query_vectors.npy", vectors)
                atomic_json(queries / "official_query_ids.json", [q["query_id"] for q in qas])
                publish_manifest(
                    queries, ["official_query_vectors.npy", "official_query_ids.json"], fingerprint
                )
                built = cache / "fixed_clean"
                built.mkdir()
                index = runner.create_index()
                runner.add_vectors(index, vectors[:1])
                runner.save_index(index, built / "index.faiss")
                (built / "metadata.jsonl").write_text(
                    json.dumps({"document_id": "test-document", "source_page_ids": [1]}) + "\n"
                )
                atomic_json(built / "ready.json", {"ntotal": 1, "dimension": 384, "run_id": runner.RUN_ID})
                atomic_json(
                    built / "profile.json",
                    {"run_id": runner.RUN_ID, "chunker": "fixed", "noise_level": "clean"},
                )
                publish_manifest(
                    built, ["index.faiss", "metadata.jsonl", "ready.json", "profile.json"], fingerprint
                )
                output = settings.storage / "test-output"
                with (
                    patch("platform_eval.research.snapshot", return_value=manifest),
                    patch("platform_eval.research.import_runner", return_value=runner),
                ):
                    result = execute(
                        settings, {"chunker": "fixed", "noise": "clean"}, fingerprint, output, "research"
                    )
                self.assertEqual(result["question_count"], 8456)
                self.assertEqual(result["context_verified_count"], 5277)
                self.assertEqual(result["hit_at_1"], 1.0)
                self.assertEqual(result["mrr_at_100"], 1.0)
                self.assertEqual(len(list((output / "parts").glob("batch_*.csv"))), 67)
                self.assertTrue(result["cache_hit"])
                self.assertFalse(list(output.rglob("*.tmp")))
        finally:
            os.chdir(previous_cwd)
