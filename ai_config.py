from __future__ import annotations

import os
from dataclasses import dataclass


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
        """Build config from environment variables.

        This is the *only* place in the project that reads env vars.
        """
        return cls(
            enabled=True,
            api_key=os.environ.get("AI_API_KEY", ""),
            base_url=os.environ.get("AI_BASE_URL", ""),
            model=os.environ.get("AI_MODEL", ""),
            endpoint=os.environ.get("AI_ENDPOINT", "/chat/completions"),
        )
