from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    default_provider: str = "deepseek"
    default_model_override: str | None = None
    target_language: str = "Chinese"
    concurrency: int = 4
    retry_count: int = 3
    timeout: int = 300
    output_directory: Path = Path("./output")
    enable_cache: bool = True
    log_level: str = "INFO"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.default_provider:
            errors.append("default_provider is required")
        if self.concurrency <= 0:
            errors.append("concurrency must be greater than 0")
        if self.retry_count < 0:
            errors.append("retry_count must be greater than or equal to 0")
        if self.timeout <= 0:
            errors.append("timeout must be greater than 0")
        if not str(self.output_directory):
            errors.append("output_directory is required")
        return errors


def default_settings_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "settings.toml"


def load_settings(settings_path: Path | None = None) -> Settings:
    path = settings_path or default_settings_path()
    raw_settings: dict[str, Any] = {}
    if path.exists():
        with path.open("rb") as file:
            raw_settings = tomllib.load(file)

    settings = Settings(
        default_provider=str(raw_settings.get("default_provider") or Settings.default_provider),
        default_model_override=_optional_str(raw_settings.get("default_model_override")),
        target_language=str(raw_settings.get("target_language") or Settings.target_language),
        concurrency=int(raw_settings.get("concurrency", Settings.concurrency)),
        retry_count=int(raw_settings.get("retry_count", Settings.retry_count)),
        timeout=int(raw_settings.get("timeout", Settings.timeout)),
        output_directory=Path(str(raw_settings.get("output_directory") or Settings.output_directory)),
        enable_cache=bool(raw_settings.get("enable_cache", Settings.enable_cache)),
        log_level=str(raw_settings.get("log_level") or Settings.log_level),
    )
    errors = settings.validate()
    if errors:
        raise ValueError(f"settings error: {', '.join(errors)}")
    settings.output_directory.mkdir(parents=True, exist_ok=True)
    return settings


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
