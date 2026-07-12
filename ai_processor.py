from __future__ import annotations

import logging

from ai_config import AIServiceConfig
from ai_model import AIConfig
from ai_service import AIService, AIServiceError

logger = logging.getLogger(__name__)


def analyze_articles(articles: list[dict], config: AIConfig) -> list[dict]:
    """Attach analysis results to each article in-place.

    Sprint 2 behaviour:
      - If AIServiceConfig is active (has api_key + base_url),
        summarise the **first** article only and store it in
        article["ai_summary"].
      - Otherwise keep the existing no-op path.
    """
    if not config.enabled:
        return articles

    # Load configuration exclusively from ai_config (env vars).
    ai_cfg = AIServiceConfig.from_env()

    if ai_cfg.is_active and articles:
        _summarize_first(articles[0], ai_cfg)

    return articles


def _summarize_first(article: dict, ai_cfg: AIServiceConfig) -> None:
    """Call the AI and attach the summary to article."""
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
        article["ai_summary"] = None
        return

    try:
        svc = AIService(ai_cfg)
        article["ai_summary"] = svc.summarize(text)
    except AIServiceError as exc:
        logger.warning("AI summarisation failed: %s", exc)
        article["ai_summary"] = None
