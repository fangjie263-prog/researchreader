from __future__ import annotations

from collections.abc import Callable

from ..config import ProviderConfig
from .base import Provider
from .openai_compatible import OpenAICompatibleProvider

ProviderBuilder = Callable[[ProviderConfig], Provider]


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderBuilder] = {}

    @classmethod
    def default(cls) -> "ProviderRegistry":
        registry = cls()
        registry.register("openai-compatible", OpenAICompatibleProvider)
        return registry

    def register(self, kind: str, provider: ProviderBuilder) -> None:
        self._providers[kind] = provider

    def get(self, kind: str) -> ProviderBuilder | None:
        return self._providers.get(kind)
