"""Compatibility boundary around the unchanged research runner.

Executed only in a dedicated child process. No historical output paths are used.
"""

import csv
import importlib.util
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

from filelock import FileLock

from .contracts import identity
from .inputs import snapshot
from .storage import atomic_json, publish_manifest, valid_manifest

CACHE_FILES = ("index.faiss", "metadata.jsonl", "ready.json", "profile.json")
QUERY_FILES = ("official_query_vectors.npy", "official_query_ids.json")


def import_runner(settings):
    sys.dont_write_bytecode = True
    os.chdir(settings.research)
    sys.path.insert(0, str(settings.research / "src"))
    spec = importlib.util.spec_from_file_location(
        "isolated_research_runner", settings.research / "run_experiment.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def quarantine(directory):
    if directory.exists():
        directory.rename(directory.with_name(directory.name + ".invalid-" + uuid.uuid4().hex))
    directory.mkdir(parents=True)


def validate_result(result, task, fingerprint, expected_count):
    import math

    if (
        result["fingerprint"] != fingerprint
        or result["chunker"] != task["chunker"]
        or result["noise"] != task["noise"]
        or result["question_count"] != expected_count
    ):
        raise ValueError("Result identity/count mismatch")
    for key in ("hit_at_1", "hit_at_5", "mrr_at_100"):
        value = result[key]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Invalid retrieval metric")
    if result["hit_at_1"] > result["hit_at_5"]:
        raise ValueError("Hit@1 cannot exceed Hit@5")
    return result


def execute(settings, task, fingerprint, output, mode, cache_namespace="shared"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if identity(snapshot(settings, mode)) != fingerprint:
        raise ValueError("Source/data/model/dependency identity changed after job submission")
    if mode == "fixture":
        if not settings.allow_fixture:
            raise ValueError("Engineering fixture disabled")
        result = {
            "fingerprint": fingerprint,
            "chunker": task["chunker"],
            "noise": task["noise"],
            "question_count": 2,
            "hit_at_1": 0.5,
            "hit_at_5": 1.0,
            "mrr_at_100": 0.75,
            "scope": "engineering-fixture-NOT-research",
            "cache_hit": False,
        }
        atomic_json(output / "result.json", result)
        publish_manifest(output, ["result.json"], fingerprint)
        return result
    atomic_json(output / "progress.json", {"stage": "loading_research"})
    runner = import_runner(settings)
    if mode == "smoke":
        if not settings.allow_fixture:
            raise ValueError("Engineering smoke corpus disabled")
        from .smoke import execute_smoke

        return execute_smoke(settings, task, fingerprint, output, runner, cache_namespace)
    cache_root = settings.storage / "cache" / cache_namespace / fingerprint
    cache_root.mkdir(parents=True, exist_ok=True)
    cache = cache_root / f"{task['chunker']}_{task['noise']}"
    runner.INDEXES = cache_root / "queries"
    runner.INDEXES.mkdir(exist_ok=True)
    qas, _ = runner.read_qas()
    # One model at most per child; query generation is globally serialized.
    model = None
    original_loader = runner.load_embedding_model

    def load_model():
        nonlocal model
        if model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(str(settings.model_path), device="cpu", local_files_only=True)
            model.eval()
            if model.get_embedding_dimension() != 384 or model.max_seq_length != 256:
                raise ValueError("Model dimension/input budget changed")
            if model.tokenizer.num_special_tokens_to_add(pair=False) != 2:
                raise ValueError("Model special-token budget changed")
        return model

    runner.load_embedding_model = load_model
    atomic_json(output / "progress.json", {"stage": "preparing_query_vectors"})
    with FileLock(str(cache_root / "queries.lock"), timeout=settings.task_timeout):
        if not valid_manifest(runner.INDEXES, fingerprint, QUERY_FILES):
            quarantine(runner.INDEXES)
            runner.prepare_queries(qas, load_model())
            publish_manifest(runner.INDEXES, QUERY_FILES, fingerprint)
        # Existing reader still checks official IDs and shape.
        runner.prepare_queries(qas)
    paths = {
        "index": cache / "index.faiss",
        "metadata": cache / "metadata.jsonl",
        "ready": cache / "ready.json",
        "profile": cache / "profile.json",
        "parts": output / "parts",
    }
    atomic_json(output / "progress.json", {"stage": "preparing_index"})
    with FileLock(str(cache_root / (cache.name + ".lock")), timeout=settings.task_timeout):
        hit = valid_manifest(cache, fingerprint, CACHE_FILES)
        if not hit:
            quarantine(cache)
            runner.build_configuration(task["chunker"], task["noise"], paths, load_model())
            publish_manifest(cache, CACHE_FILES, fingerprint)
        runner.load_built_configuration(paths)
        shutil.copyfile(paths["profile"], output / "profile.json")
    # Immutable shared index generations are read concurrently. No pruning while active.
    paths = {**paths, "profile": output / "profile.json"}
    runner.paths_for = lambda key: paths
    model = None
    runner.load_embedding_model = original_loader
    atomic_json(output / "progress.json", {"stage": "retrieving", "total_query_batches": 67})
    runner.run_configuration(task["chunker"], task["noise"])
    count = verified = 0
    sums = [0.0, 0.0, 0.0]
    subset = [0.0, 0.0, 0.0]
    seen = set()
    expected_ids = {q["query_id"] for q in qas}
    for path in sorted(paths["parts"].glob("batch_*.csv")):
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != runner.QUERY_COLUMNS:
                raise ValueError("Query output schema changed")
            for row in reader:
                if (
                    row["query_id"] not in expected_ids
                    or row["query_id"] in seen
                    or row["chunker"] != task["chunker"]
                    or row["noise_level"] != task["noise"]
                ):
                    raise ValueError("Query identity mismatch")
                seen.add(row["query_id"])
                values = [float(row[k]) for k in ("hit_at_1", "hit_at_5", "reciprocal_rank")]
                for i, value in enumerate(values):
                    sums[i] += value
                count += 1
                if row["context_verified"] == "1":
                    verified += 1
                    for i, value in enumerate(values):
                        subset[i] += value
    if seen != expected_ids or verified != 5277:
        raise ValueError("Official QA coverage changed")
    result = {
        "fingerprint": fingerprint,
        "chunker": task["chunker"],
        "noise": task["noise"],
        "question_count": count,
        "context_verified_count": verified,
        **dict(zip(("hit_at_1", "hit_at_5", "mrr_at_100"), [v / count for v in sums])),
        "context_verified_metrics": dict(
            zip(("hit_at_1", "hit_at_5", "mrr_at_100"), [v / verified for v in subset])
        ),
        "scope": "official-OHRBench",
        "cache_hit": hit,
        "profile": json.loads(paths["profile"].read_text()),
    }
    validate_result(result, task, fingerprint, 8456)
    atomic_json(output / "result.json", result)
    publish_manifest(
        output,
        ["result.json", "profile.json", *[str(p.relative_to(output)) for p in paths["parts"].glob("*.csv")]],
        fingerprint,
    )
    return result
