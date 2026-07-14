from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .registry import ModelInfo, ModelRegistry


def default_model_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "models.toml"


def load_model_registry(registry_path: Path | None = None) -> ModelRegistry:
    path = registry_path or default_model_registry_path()
    with path.open("rb") as file:
        raw_registry = tomllib.load(file)

    models = raw_registry.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("model registry error: [models] must be a table")

    return ModelRegistry(_model_from_dict(name, raw_model) for name, raw_model in models.items())


def _model_from_dict(name: str, raw: Any) -> ModelInfo:
    if not isinstance(raw, dict):
        raise ValueError(f"model registry error: model '{name}' must be a table")
    return ModelInfo(
        name=name,
        provider=str(raw.get("provider") or ""),
        context_length=int(raw.get("context_length") or 0),
        supports_stream=bool(raw.get("supports_stream", False)),
        supports_image=bool(raw.get("supports_image", False)),
        supports_reasoning=bool(raw.get("supports_reasoning", False)),
        supports_embedding=bool(raw.get("supports_embedding", False)),
        supports_tool_call=bool(raw.get("supports_tool_call", False)),
        pricing=_optional_pricing(raw.get("pricing")),
    )


def _optional_pricing(value: object) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("model registry error: pricing must be a table")
    return {str(key): float(price) for key, price in value.items()}
