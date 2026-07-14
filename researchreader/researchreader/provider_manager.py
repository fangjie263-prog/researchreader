from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .config import ProviderConfig, load_provider_catalog
from .models import ModelInfo, ModelRegistry, load_model_registry
from .providers import ProviderCapabilities, ProviderFactory, ProviderTestResult


@dataclass(frozen=True)
class ProviderSummary:
    name: str
    display_name: str
    kind: str
    base_url: str
    model: str
    api_key_env: str
    description: str
    provider_type: str
    country: str
    website: str
    enabled: bool
    configured: bool
    configuration_errors: tuple[str, ...]
    models: tuple[ModelInfo, ...]


class ProviderManager:
    def __init__(
        self,
        configs: list[ProviderConfig],
        factory: ProviderFactory | None = None,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        self._configs = configs
        self._factory = factory or ProviderFactory()
        self._model_registry = model_registry or load_model_registry()

    @classmethod
    def from_config(cls, config_path: Path | None = None) -> "ProviderManager":
        return cls(load_provider_catalog(config_path))

    def summaries(self) -> list[ProviderSummary]:
        summaries: list[ProviderSummary] = []
        for config in self._configs:
            errors = tuple(self._configuration_errors(config))
            summaries.append(
                ProviderSummary(
                    name=config.name,
                    display_name=config.display_name,
                    kind=config.kind,
                    base_url=config.base_url,
                    model=config.model,
                    api_key_env=config.api_key_env,
                    description=config.description,
                    provider_type=config.provider_type,
                    country=config.country,
                    website=config.website,
                    enabled=config.enabled,
                    configured=config.enabled and not errors,
                    configuration_errors=errors,
                    models=tuple(self._model_registry.list_models_by_provider(config.name)),
                )
            )
        return summaries

    def test_all(self) -> list[ProviderTestResult]:
        results: list[ProviderTestResult] = []
        for config in self._configs:
            if not config.enabled:
                continue
            model_info = self._find_model(config.model)
            configuration_errors = self._configuration_errors(config)
            if configuration_errors:
                results.append(
                    ProviderTestResult(
                        provider_name=config.name,
                        display_name=config.display_name,
                        model=config.model,
                        ok=False,
                        configuration_ok=False,
                        capabilities=model_info.to_capabilities() if model_info is not None else ProviderCapabilities(),
                        errors=tuple(configuration_errors),
                    )
                )
                continue

            provider = self._factory.create(config)
            result = provider.test()
            if model_info is not None:
                result = replace(result, capabilities=model_info.to_capabilities())
            results.append(result)
        return results

    def _configuration_errors(self, config: ProviderConfig) -> list[str]:
        if not config.enabled:
            return []
        errors = config.validate()
        model_info = self._find_model(config.model)
        if model_info is not None and model_info.provider != config.name:
            errors.append(
                f"model '{config.model}' belongs to provider '{model_info.provider}', not '{config.name}'"
            )
        return errors

    def _find_model(self, name: str) -> ModelInfo | None:
        try:
            return self._model_registry.get_model(name)
        except KeyError:
            return None
