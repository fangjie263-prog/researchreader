from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..pipeline import PipelineContext, PipelineResult


class DocumentAdapter(ABC):
    """Base interface for document IO adapters."""

    document_type: str

    @abstractmethod
    def load(self, source_path: Path) -> Any:
        """Load a document from disk."""

    @abstractmethod
    def save(self, document: Any, output_path: Path) -> None:
        """Save a document to disk."""

    @abstractmethod
    def detect(self, source_path: Path) -> bool:
        """Return whether this adapter can handle the source path."""

    @abstractmethod
    def metadata(self, document: Any) -> dict[str, Any]:
        """Return document metadata."""


class TranslationAdapter(ABC):
    """Base interface for translation adapters."""

    document_type: str

    @abstractmethod
    def translate(self, context: PipelineContext) -> PipelineResult:
        """Translate through the current pipeline context."""
