"""Golden retrieval cases for pgvector hyperparameter sweeps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Golden(BaseModel):
    """A hand-curated question and expected retrieval evidence."""

    model_config = ConfigDict(frozen=True)

    question: str
    expected_output: str
    expected_retrieval_context: list[str] = Field(default_factory=list)
    metadata_filter: dict[str, Any] = Field(default_factory=dict)


def load_goldens(path: str | Path) -> list[Golden]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Golden dataset must be a JSON array.")
    return [Golden.model_validate(item) for item in data]
