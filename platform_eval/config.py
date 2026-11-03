"""Explicit single-host defaults, shared by API, dispatcher and workers."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    storage: Path = field(default_factory=lambda: Path(os.getenv("RAG_STORAGE", "./var/platform")).resolve())
    research: Path = field(
        default_factory=lambda: Path(os.getenv("RAG_RESEARCH_ROOT", "../rag_chunk_robustness")).resolve()
    )
    broker: str = field(default_factory=lambda: os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
    model_path: Path = field(
        default_factory=lambda: Path(os.getenv("RAG_MODEL_PATH", "./var/model")).resolve()
    )
    max_pending: int = field(default_factory=lambda: int(os.getenv("RAG_MAX_PENDING", "64")))
    lease_seconds: int = field(default_factory=lambda: int(os.getenv("RAG_LEASE_SECONDS", "90")))
    max_attempts: int = 3
    task_timeout: int = field(default_factory=lambda: int(os.getenv("RAG_TASK_TIMEOUT", "21600")))
    allow_fixture: bool = field(default_factory=lambda: os.getenv("RAG_ALLOW_FIXTURE", "0") == "1")

    @property
    def database(self):
        return self.storage / "metadata.sqlite3"
