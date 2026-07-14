from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PipelineContext:
    task: str = "translation"
    provider: str = ""
    model: str = ""
    target_language: str | None = None
    working_directory: Path | None = None
    runtime_options: dict[str, Any] = field(default_factory=dict)
    adapter: str | None = None
    source_path: Path | None = None
    output_path: Path | None = None
    resolved_provider: Any | None = None
