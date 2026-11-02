"""Atomic JSON publication and checked, content-addressed artifact manifests."""

import hashlib
import json
import os
import uuid
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w") as stream:
            json.dump(value, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def publish_manifest(directory, names, fingerprint):
    atomic_json(
        Path(directory) / "checksums.json",
        {
            "fingerprint": fingerprint,
            "files": {name: sha256(Path(directory) / name) for name in sorted(names)},
        },
    )


def valid_manifest(directory, fingerprint, required):
    try:
        manifest = json.loads((Path(directory) / "checksums.json").read_text())
        return (
            manifest["fingerprint"] == fingerprint
            and set(manifest["files"]) == set(required)
            and all(sha256(Path(directory) / name) == digest for name, digest in manifest["files"].items())
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False
