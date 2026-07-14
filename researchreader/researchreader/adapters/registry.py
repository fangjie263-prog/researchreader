from __future__ import annotations

from collections.abc import Iterable

from .base import DocumentAdapter


class AdapterRegistry:
    def __init__(self, include_defaults: bool = True) -> None:
        self._adapters: dict[str, type[DocumentAdapter]] = {}
        if include_defaults:
            self._register_defaults()

    def register_adapter(self, document_type: str, adapter_class: type[DocumentAdapter]) -> None:
        normalized_type = _normalize_document_type(document_type)
        if normalized_type in self._adapters:
            raise ValueError(f"adapter already registered for document type: {normalized_type}")
        if not issubclass(adapter_class, DocumentAdapter):
            raise TypeError("adapter_class must inherit from DocumentAdapter")
        self._adapters[normalized_type] = adapter_class

    def get_adapter(self, document_type: str) -> type[DocumentAdapter]:
        normalized_type = _normalize_document_type(document_type)
        adapter_class = self._adapters.get(normalized_type)
        if adapter_class is None:
            raise KeyError(f"unknown document adapter: {normalized_type}")
        return adapter_class

    def list_adapters(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def _register_defaults(self) -> None:
        from .epub import EPUBAdapter

        self.register_adapter("epub", EPUBAdapter)


def _normalize_document_type(document_type: str) -> str:
    return document_type.lower().lstrip(".")
