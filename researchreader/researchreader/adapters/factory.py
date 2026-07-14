from __future__ import annotations

from pathlib import Path

from .base import DocumentAdapter
from .registry import AdapterRegistry


class AdapterFactory:
    def __init__(self, registry: AdapterRegistry | None = None) -> None:
        self._registry = registry or AdapterRegistry()

    def create_for_path(self, source_path: Path | str) -> DocumentAdapter:
        path = Path(source_path)
        document_type = _document_type_from_suffix(path)
        adapter_class = self._registry.get_adapter(document_type)
        return adapter_class()


def _document_type_from_suffix(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "md":
        return "markdown"
    if suffix == "htm":
        return "html"
    return suffix
