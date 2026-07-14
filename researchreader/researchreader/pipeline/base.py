from __future__ import annotations

from abc import ABC, abstractmethod

from .context import PipelineContext
from .result import PipelineResult


class Pipeline(ABC):
    """Base interface for future ResearchReader pipelines."""

    @abstractmethod
    def run(self, context: PipelineContext) -> PipelineResult:
        """Execute a pipeline with the provided context."""
