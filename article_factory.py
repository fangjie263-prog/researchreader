"""Conversion boundary between legacy parser dictionaries and Article."""
from __future__ import annotations

from typing import Any

from models import Article


class ArticleFactory:
    @staticmethod
    def from_dict(data: dict[str, Any]) -> Article:
        metadata = dict(data.get("metadata", {}))
        if data.get("article_id"):
            metadata.setdefault("article_id", data["article_id"])
        return Article(
            uuid=str(data.get("uuid", "")), title=str(data.get("title", "")),
            subtitle=str(data.get("subtitle", "")), author=str(data.get("author", data.get("byline", ""))),
            source=str(data.get("source", data.get("source_document", data.get("_source", "")))),
            paragraphs=list(data.get("paragraphs", [])), images=list(data.get("images", [])),
            metadata=metadata, language=str(data.get("language", "unknown")),
            publication=data.get("publication"), source_type=str(data.get("source_type", "epub")),
            quality_score=int(data.get("quality_score", 100)), warnings=list(data.get("warnings", [])),
        )

    @staticmethod
    def to_dict(article: Article) -> dict[str, Any]:
        data = {
            "uuid": article.uuid, "article_id": article.article_id, "title": article.title,
            "subtitle": article.subtitle, "author": article.author, "byline": article.author,
            "source": article.source, "source_document": article.source, "paragraphs": list(article.paragraphs),
            "images": list(article.images), "metadata": dict(article.metadata), "language": article.language,
            "publication": article.publication, "source_type": article.source_type,
            "quality_score": article.quality_score, "warnings": list(article.warnings),
        }
        return data
