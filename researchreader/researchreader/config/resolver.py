from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..models import ModelRegistry, load_model_registry
from ..providers import ProviderCapabilities
from .loader import load_provider_catalog
from .models import ProviderConfig
from .settings import Settings, load_settings


@dataclass(frozen=True)
class ResolvedProvider:
    id: str
    display_name: str
    base_url: str
    api_key: str | None
    model: str
    provider_type: str
    capabilities: ProviderCapabilities
    model_source: str
    config: ProviderConfig


class ProviderResolver:
    def __init__(
        self,
        settings: Settings | None = None,
        provider_catalog_path: Path | None = None,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        self._settings = settings or load_settings()
        self._providers = {provider.name: provider for provider in load_provider_catalog(provider_catalog_path)}
        self._model_registry = model_registry or load_model_registry()

    @property
    def settings(self) -> Settings:
        return self._settings

    def resolve(self, provider: str | None = None, model: str | None = None) -> ResolvedProvider:
        provider_id = provider or self._settings.default_provider
        provider_config = self._providers.get(provider_id)
        if provider_config is None:
            raise ValueError(f"unknown provider: {provider_id}")
        if not provider_config.enabled:
            raise ValueError(f"provider is disabled: {provider_id}")

        resolved_model, model_source = self._resolve_model(provider_config, model)
        model_info = self._find_model(resolved_model)
        return ResolvedProvider(
            id=provider_config.name,
            display_name=provider_config.display_name,
            base_url=provider_config.base_url,
            api_key=provider_config.resolved_api_key,
            model=resolved_model,
            provider_type=provider_config.provider_type,
            capabilities=model_info.to_capabilities() if model_info else ProviderCapabilities(),
            model_source=model_source,
            config=provider_config,
        )

    def _resolve_model(self, provider_config: ProviderConfig, explicit_model: str | None) -> tuple[str, str]:
        if explicit_model:
            return explicit_model, "PipelineContext"
        if self._settings.default_model_override:
            return self._settings.default_model_override, "settings override"
        if provider_config.model:
            return provider_config.model, "provider default"
        return "auto", "provider built-in default"

    def _find_model(self, name: str):
        try:
            return self._model_registry.get_model(name)
        except KeyError:
            return None
