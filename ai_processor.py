from __future__ import annotations

import json
import logging

from ai_config import AIServiceConfig
from ai_model import AIConfig
from ai_service import AIService, AIServiceError
from topic_manager import topic_context

logger = logging.getLogger(__name__)


def analyze_articles(articles: list[dict], config: AIConfig) -> list[dict]:
    """Attach analysis results to each article in-place."""

    if not config.enabled:
        return articles

    ai_cfg = AIServiceConfig.from_env()

    if ai_cfg.is_active:
        context = topic_context()
        for article in articles:
            _summarize_article(article, ai_cfg, context)

    return articles


def _summarize_article(article: dict, ai_cfg: AIServiceConfig, topics: str = "") -> None:
    """Call the AI and attach the parsed analysis."""

    parts: list[str] = []

    if article.get("title"):
        parts.append(article["title"])

    if article.get("subtitle"):
        parts.append(article["subtitle"])

    if article.get("annotation"):
        parts.append(article["annotation"])

    for para in article.get("paragraphs", [])[:10]:
        parts.append(para)

    text = "\n\n".join(parts)

    if not text.strip():
        article["analysis"] = None
        return

    try:
        svc = AIService(ai_cfg)

        raw = svc.summarize(text, topic_context=topics)

        parsed = json.loads(raw)

        if isinstance(parsed, dict):
            article["analysis"] = parsed
            print(">>>", article["analysis"])
            print(">>> Stored analysis")
            print(article["analysis"])
        else:
            article["analysis"] = None

    except (AIServiceError, json.JSONDecodeError) as exc:
        logger.warning("AI summarisation failed: %s", exc)
        article["analysis"] = None
