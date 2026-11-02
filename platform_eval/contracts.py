"""Strict request contracts; no model inference during submission."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CHUNKERS = ("fixed", "recursive", "semantic", "structure")
NOISES = ("clean", "mild", "moderate", "severe")


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    chunker: Literal["fixed", "recursive", "semantic", "structure"]
    noise: Literal["clean", "mild", "moderate", "severe"]


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    configurations: list[Configuration] = Field(min_length=1, max_length=16)
    mode: Literal["research", "smoke", "fixture"] = "research"

    @model_validator(mode="after")
    def unique_configurations(self):
        if len(set(self.configurations)) != len(self.configurations):
            raise ValueError("Duplicate configuration")
        if self.mode == "smoke" and any(c.noise != "clean" for c in self.configurations):
            raise ValueError("Small real-RAG smoke corpus supports clean only")
        return self
