"""Locate recommendation records by their stable article ID."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_JSON_PATH = ROOT / "output" / "reading_recommendations.json"
REQUIRED_FIELDS = {
    "article_id",
    "title",
    "priority",
    "matched_topics",
    "summary_zh",
    "summary_en",
    "reason_zh",
    "reason_en",
    "source_document",
}


class ArticleNotFound(LookupError):
    """Raised when a recommendation does not contain the requested ID."""


class ArticleLocator:
    def __init__(self, json_path: Path | str = DEFAULT_JSON_PATH) -> None:
        self.json_path = Path(json_path)
        self._articles = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.json_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"Recommendation JSON not found: {self.json_path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid recommendation JSON: {self.json_path}") from exc

        if not isinstance(data, list):
            raise ValueError("Recommendation JSON must contain an array of articles")

        articles: dict[str, dict[str, Any]] = {}
        for index, article in enumerate(data, start=1):
            if not isinstance(article, dict):
                raise ValueError(f"Article record {index} must be an object")
            missing = REQUIRED_FIELDS - article.keys()
            if missing:
                names = ", ".join(sorted(missing))
                raise ValueError(f"Article record {index} is missing fields: {names}")
            article_id = article["article_id"]
            if not isinstance(article_id, str) or not article_id:
                raise ValueError(f"Article record {index} has an invalid article_id")
            if article_id in articles:
                raise ValueError(f"Duplicate article_id in recommendation JSON: {article_id}")
            articles[article_id] = article
        return articles

    def get(self, article_id: str) -> dict[str, Any]:
        try:
            return self._articles[article_id]
        except KeyError as exc:
            raise ArticleNotFound(f"Article not found: {article_id}") from exc
