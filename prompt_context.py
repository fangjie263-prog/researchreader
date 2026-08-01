"""Normalize Article and legacy dictionaries for prompt templates."""
from __future__ import annotations

from typing import Any


class PromptContext:
    @staticmethod
    def from_article(article: Any, topics: Any = "") -> dict[str, Any]:
        def get(name: str, default: Any = "") -> Any:
            if isinstance(article, dict):
                return article.get(name, default)
            return getattr(article, name, default)

        paragraphs = get("paragraphs", [])
        paragraphs = [p.get("text", "") if isinstance(p, dict) else str(p) for p in paragraphs]
        metadata = get("metadata", {}) or {}
        return {
            "title": get("title"), "subtitle": get("subtitle"),
            "author": get("author", get("byline", "")),
            "publication": get("publication", ""), "language": get("language", "unknown"),
            "paragraphs": "\n\n".join(paragraphs), "topics": topics,
            "metadata": metadata,
        }
