from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_SETTINGS_PATH = ROOT / "ai_settings.json"


@dataclass(slots=True, frozen=True)
class AIServiceConfig:
    """Immutable configuration for the AI reading layer.

    Parameters
    ----------
    enabled:
        Whether the AI layer is turned on at all.
    api_key:
        Provider API key.
    base_url:
        Full provider endpoint, e.g. ``https://api.agnes.ai/v1``.
        Must be set for the service to activate.
    model:
        Model identifier sent to the provider.
    endpoint:
        API endpoint path appended to ``base_url``.
        Defaults to ``/chat/completions``.
    """

    enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    endpoint: str = "/chat/completions"

    @property
    def is_active(self) -> bool:
        """Return True only when we have everything needed to make a call."""
        return self.enabled and bool(self.api_key) and bool(self.base_url)

    @classmethod
    def from_env(cls) -> "AIServiceConfig":
        """Load local settings first, then let environment variables override them."""
        settings_path = Path(os.environ.get("AI_SETTINGS_PATH", DEFAULT_SETTINGS_PATH))
        data: dict = {}
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        def value(name: str, fallback: str) -> str:
            override = os.environ.get(name)
            return override if override else fallback

        return cls(
            enabled=os.environ.get("AI_ENABLED", str(data.get("enabled", True))).lower() not in {"0", "false", "no"},
            api_key=value("AI_API_KEY", data.get("api_key", "")),
            base_url=value("AI_BASE_URL", data.get("base_url", "")),
            model=value("AI_MODEL", data.get("model", "")),
            endpoint=value("AI_ENDPOINT", data.get("endpoint", "/chat/completions")),
        )

    def save(self, path: Path | None = None) -> Path:
        """Save local settings without exposing them to source control."""
        target = path or DEFAULT_SETTINGS_PATH
        target.write_text(
            json.dumps({
                "enabled": self.enabled,
                "api_key": self.api_key,
                "base_url": self.base_url,
                "model": self.model,
                "endpoint": self.endpoint,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target
