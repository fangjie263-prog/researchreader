from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .models import ProviderConfig


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "providers"


def load_provider_configs(config_path: Path | None = None, include_disabled: bool = False) -> list[ProviderConfig]:
    configs = load_provider_catalog(config_path)
    if include_disabled:
        return configs
    return [config for config in configs if config.enabled]


def load_provider_catalog(config_path: Path | None = None) -> list[ProviderConfig]:
    path = config_path or default_config_path()
    raw_providers = _load_raw_provider_tables(path)

    seen_ids: set[str] = set()
    configs: list[ProviderConfig] = []
    for name, raw_provider in raw_providers:
        config = _provider_from_dict(name, raw_provider)
        if config.name in seen_ids:
            raise ValueError(f"configuration error: duplicated provider id: {config.name}")
        seen_ids.add(config.name)
        errors = _validate_required_fields(config)
        if errors:
            raise ValueError(f"configuration error: provider '{config.name}': {', '.join(errors)}")
        configs.append(config)
    return configs


def _provider_from_dict(name: str, raw: dict[str, Any]) -> ProviderConfig:
    provider_id = str(raw.get("id") or name)
    return ProviderConfig(
        name=provider_id,
        display_name=str(raw.get("display_name") or provider_id),
        kind=str(raw.get("kind") or ""),
        base_url=str(raw.get("base_url") or ""),
        model=str(raw.get("default_model") or raw.get("model") or ""),
        api_key_env=str(raw.get("api_key_env") or ""),
        description=str(raw.get("description") or ""),
        provider_type=_provider_type(raw.get("provider_type")),
        country=str(raw.get("country") or ""),
        website=str(raw.get("website") or ""),
        enabled=bool(raw.get("enabled", True)),
        api_key=_optional_str(raw.get("api_key")),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _provider_type(value: object) -> str:
    provider_type = str(value or "custom").lower()
    if provider_type in ("official", "gateway", "custom"):
        return provider_type
    return "custom"


def _iter_provider_tables(providers: dict[str, Any] | list[Any]):
    if isinstance(providers, dict):
        for name, raw_provider in providers.items():
            if not isinstance(raw_provider, dict):
                raise ValueError(f"configuration error: provider '{name}' must be a table")
            yield str(name), raw_provider
    else:
        for index, raw_provider in enumerate(providers):
            if not isinstance(raw_provider, dict):
                raise ValueError(f"configuration error: provider at index {index} must be a table")
            yield str(index), raw_provider


def _load_raw_provider_tables(path: Path) -> list[tuple[str, dict[str, Any]]]:
    if path.is_dir():
        provider_files = sorted(path.glob("*.toml"))
        tables: list[tuple[str, dict[str, Any]]] = []
        for provider_file in provider_files:
            with provider_file.open("rb") as file:
                raw_config = tomllib.load(file)
            if "providers" in raw_config:
                raise ValueError(
                    f"configuration error: provider catalog file '{provider_file.name}' must contain exactly one provider"
                )
            tables.append((provider_file.stem, raw_config))
        return tables

    with path.open("rb") as file:
        raw_config = tomllib.load(file)
    providers = raw_config.get("providers")
    if providers is None:
        return [(path.stem, raw_config)]
    if not isinstance(providers, (dict, list)):
        raise ValueError("configuration error: providers must be a table or array of tables")
    return list(_iter_provider_tables(providers))


def _validate_required_fields(config: ProviderConfig) -> list[str]:
    errors: list[str] = []
    if not config.name:
        errors.append("missing id")
    if not config.display_name:
        errors.append("missing display_name")
    if not config.kind:
        errors.append("missing kind")
    if config.kind != "openai-compatible":
        errors.append(f"unsupported provider kind: {config.kind}")
    if not config.base_url:
        errors.append("missing base_url")
    if not config.api_key_env and not config.api_key:
        errors.append("missing api_key_env or api_key")
    if not config.model:
        errors.append("missing default_model")
    return errors
