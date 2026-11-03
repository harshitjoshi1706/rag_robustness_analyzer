"""Freeze byte identities, including model weights/tokenizer and numeric libraries."""

import importlib.metadata
import json
import platform
from pathlib import Path

from .contracts import identity
from .storage import atomic_json, sha256

NUMERIC_PACKAGES = (
    "numpy",
    "faiss-cpu",
    "torch",
    "sentence-transformers",
    "transformers",
    "tokenizers",
    "langchain-text-splitters",
    "pandas",
    "pyarrow",
    "nltk",
    "scipy",
    "scikit-learn",
)


def snapshot(settings, mode="research"):
    if mode == "fixture":
        return {"scope": "engineering-fixture-v1", "scientific": False}
    files = {}
    root = settings.research
    paths = [
        root / "run_experiment.py",
        *sorted((root / "src").glob("*.py")),
    ]
    if mode == "research":
        paths.extend([root / "data/raw/OHR-Bench_v2.parquet", root / "data/raw/qas_v2.json"])
    if not (settings.model_path / "config.json").is_file():
        raise FileNotFoundError("Prepare the pinned MiniLM model using scripts/prepare_model.py")
    for path in paths:
        files["research/" + str(path.relative_to(root))] = sha256(path)
    package = Path(__file__).parent
    for path in [
        *[p for p in sorted((package / "data").rglob("*")) if p.is_file()],
        *sorted(package.glob("*.py")),
    ]:
        files["platform/" + str(path.relative_to(package))] = sha256(path)
    for path in sorted(settings.model_path.rglob("*")):
        if path.is_file() and ".cache" not in path.parts:
            files["model/" + str(path.relative_to(settings.model_path))] = sha256(path)
    baseline = json.loads((package / "data/scientific_baseline.json").read_text())
    expected = {"model/" + name: digest for name, digest in baseline["model"].items()}
    if mode == "research":
        expected.update({"research/" + name: digest for name, digest in baseline["research_data"].items()})
    if any(files.get(name) != digest for name, digest in expected.items()):
        raise ValueError("Model or dataset bytes differ from the frozen scientific baseline")
    return {
        "scope": "ohrbench_minilm_254_v1" if mode == "research" else "real-RAG-smoke-v1-NOT-OHRBench",
        "files": files,
        "packages": {name: importlib.metadata.version(name) for name in NUMERIC_PACKAGES},
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.system(),
            "machine": platform.machine(),
        },
    }


def freeze(settings, mode):
    manifest = snapshot(settings, mode)
    fingerprint = identity(manifest)
    atomic_json(settings.storage / "inputs" / f"{fingerprint}.json", manifest)
    return fingerprint
