from ai_model import AIConfig


def analyze_articles(articles: list[dict], config: AIConfig) -> list[dict]:
    """Attach analysis results to each article in-place.

    For Sprint 2 this is a no-op: sets ``article["analysis"] = None``.
    """
    if not config.enabled:
        return articles

    for article in articles:
        article["analysis"] = None

    return articles
