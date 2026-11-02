"""Small real MiniLM/FAISS diagnostic; never interpreted as OHRBench research."""

import json
from pathlib import Path

from filelock import FileLock

from .storage import atomic_json, publish_manifest, valid_manifest


def execute_smoke(settings, task, fingerprint, output, runner, cache_namespace="shared"):
    import numpy as np
    from sentence_transformers import SentenceTransformer

    fixture = json.loads((Path(__file__).parent / "data/smoke.json").read_text())
    qas = fixture["qas"]
    root = settings.storage / "cache" / cache_namespace / fingerprint
    root.mkdir(parents=True, exist_ok=True)
    directory = root / task["chunker"]
    files = ["index.faiss", "chunks.json"]
    model = None

    def get_model():
        nonlocal model
        if model is None:
            model = SentenceTransformer(str(settings.model_path), device="cpu", local_files_only=True)
            model.eval()
        return model

    with FileLock(str(root / "queries.lock"), timeout=60):
        queries = root / "queries"
        if not valid_manifest(queries, fingerprint, ["vectors.npy"]):
            queries.mkdir(exist_ok=True)
            np.save(
                queries / "vectors.npy", runner.embed_chunk_texts([q["question"] for q in qas], get_model())
            )
            publish_manifest(queries, ["vectors.npy"], fingerprint)
        vectors = np.load(queries / "vectors.npy")
    with FileLock(str(root / (task["chunker"] + ".lock")), timeout=60):
        hit = valid_manifest(directory, fingerprint, files)
        if not hit:
            directory.mkdir(exist_ok=True)
            chunks = []
            for document in fixture["documents"]:
                chunks.extend(
                    runner.chunk_document(document, task["chunker"], get_model().tokenizer, get_model())
                )
            index = runner.create_index()
            runner.add_vectors(index, runner.embed_chunk_texts([c["text"] for c in chunks], get_model()))
            runner.save_index(index, directory / "index.faiss")
            atomic_json(directory / "chunks.json", chunks)
            publish_manifest(directory, files, fingerprint)
        chunks = json.loads((directory / "chunks.json").read_text())
        index = runner.load_index(directory / "index.faiss")
    rankings = []
    rows = []
    for qa, vector in zip(qas, vectors, strict=True):
        ranking = runner.retrieve_one(index, chunks, vector, 100)
        ordered = [chunk for _, chunk in ranking]
        rankings.append({"query_id": qa["query_id"], "chunk_ids": [c["chunk_id"] for c in ordered]})
        rows.append({"query_id": qa["query_id"], **runner.score_ranking(ordered, qa)})
    result = {
        "fingerprint": fingerprint,
        "chunker": task["chunker"],
        "noise": task["noise"],
        "question_count": len(qas),
        "scope": "real-RAG-smoke-NOT-OHRBench",
        "cache_hit": hit,
        "hit_at_1": sum(r["hit_at_1"] for r in rows) / len(qas),
        "hit_at_5": sum(r["hit_at_5"] for r in rows) / len(qas),
        "mrr_at_100": sum(r["reciprocal_rank"] for r in rows) / len(qas),
        "rankings": rankings,
        "per_question": rows,
        "chunk_count": len(chunks),
    }
    atomic_json(output / "result.json", result)
    publish_manifest(output, ["result.json"], fingerprint)
    return result
