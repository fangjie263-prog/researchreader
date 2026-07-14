from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .models import ProviderConfig


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "default.toml"


def load_provider_configs(config_path: Path | None = None) -> list[ProviderConfig]:
    path = config_path or default_config_path()
    with path.open("rb") as file:
        raw_config = tomllib.load(file)

    providers = raw_config.get("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("configuration error: [providers] must be a table")

    configs: list[ProviderConfig] = []
    for name, raw_provider in providers.items():
        if not isinstance(raw_provider, dict):
            raise ValueError(f"configuration error: provider '{name}' must be a table")
        configs.append(_provider_from_dict(name, raw_provider))
    return configs


def _provider_from_dict(name: str, raw: dict[str, Any]) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        display_name=str(raw.get("display_name") or name),
        kind=str(raw.get("kind") or ""),
        base_url=str(raw.get("base_url") or ""),
        model=str(raw.get("model") or ""),
        api_key_env=str(raw.get("api_key_env") or ""),
        api_key=_optional_str(raw.get("api_key")),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
