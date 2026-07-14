from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    display_name: str
    kind: str
    base_url: str
    model: str
    api_key_env: str
    description: str = ""
    provider_type: str = "custom"
    country: str = ""
    website: str = ""
    enabled: bool = True
    api_key: str | None = None

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name:
            errors.append("missing provider id")
        if not self.display_name:
            errors.append("missing display_name")
        if not self.kind:
            errors.append("missing provider kind")
        if self.kind != "openai-compatible":
            errors.append(f"unsupported provider kind: {self.kind}")
        if not self.base_url:
            errors.append("missing base_url")
        if not self.model:
            errors.append("missing model")
        if not self.api_key_env and not self.api_key:
            errors.append("missing api_key_env or api_key")
        if self.api_key_env and not self.resolved_api_key:
            errors.append(f"missing API key environment variable: {self.api_key_env}")
        return errors
