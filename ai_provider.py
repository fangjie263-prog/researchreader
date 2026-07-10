from __future__ import annotations

from abc import ABC, abstractmethod

from ai_model import AIConfig


class AIProvider(ABC):
    """Interface that all AI providers must implement."""

    @abstractmethod
    def analyze(self, articles: list[dict], config: AIConfig) -> list[dict]:
        """Analyze articles and attach results in-place. Returns the list."""


class NoOpProvider(AIProvider):
    """Default no-op provider that preserves existing behavior."""

    def analyze(self, articles: list[dict], config: AIConfig) -> list[dict]:
        if not config.enabled:
            return articles
        for article in articles:
            article["analysis"] = None
        return articles
