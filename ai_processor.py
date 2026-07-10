from ai_model import AIConfig
from ai_provider import NoOpProvider


def analyze_articles(articles: list[dict], config: AIConfig) -> list[dict]:
    """Attach analysis results to each article in-place.

    For Sprint 4 this delegates to NoOpProvider.
    """
    return NoOpProvider().analyze(articles, config)
