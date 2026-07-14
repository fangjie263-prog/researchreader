from __future__ import annotations

from ..config import ProviderConfig
from .base import Provider
from .registry import ProviderRegistry
from .unsupported import UnsupportedProvider


class ProviderFactory:
    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self._registry = registry or ProviderRegistry.default()

    def create(self, config: ProviderConfig) -> Provider:
        provider_class = self._registry.get(config.kind)
        if provider_class is None:
            return UnsupportedProvider(config)
        return provider_class(config)
