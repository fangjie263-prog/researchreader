from __future__ import annotations

import json
import logging

from ai_config import AIServiceConfig
from ai_model import AIConfig
from ai_service import AIService, AIServiceError

logger = logging.getLogger(__name__)


def analyze_articles(articles: list[dict], config: AIConfig) -> list[dict]:
    """Attach analysis results to each article in-place."""

    if not config.enabled:
        return articles

    ai_cfg = AIServiceConfig.from_env()

    if ai_cfg.is_active and articles:
        _summarize_first(articles[0], ai_cfg)

    return articles


def _summarize_first(article: dict, ai_cfg: AIServiceConfig) -> None:
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

        raw = svc.summarize(text)

        parsed = json.loads(raw)

        if isinstance(parsed, dict):
            article["analysis"] = parsed
        else:
            article["analysis"] = None

    except (AIServiceError, json.JSONDecodeError) as exc:
        logger.warning("AI summarisation failed: %s", exc)
        article["analysis"] = None