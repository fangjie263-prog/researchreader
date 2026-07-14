from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class PipelineStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class PipelineResult:
    status: PipelineStatus
    task: str
    artifacts: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: float | None = None

    @property
    def ok(self) -> bool:
        return self.status == PipelineStatus.SUCCESS
