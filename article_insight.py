"""Structured article-level AI insight generation and rendering."""
from __future__ import annotations

from typing import Any

from models import ArticleInsight
from prompt_context import PromptContext
from prompt_manager import PromptManager

FIELDS = ("summary", "why_it_matters", "market_impact", "risks", "follow_up_questions")


class ArticleInsightError(Exception):
    pass


class ArticleInsightBuilder:
    def __init__(self, service: Any):
        self.service = service

    def build_context(self, article: Any) -> dict[str, Any]:
        context = PromptContext.from_article(article)
        picks = article.get("research_picks", {}) if isinstance(article, dict) else {}
        context["companies"] = ", ".join(picks.get("companies", [])) if isinstance(picks, dict) else ""
        context["sectors"] = ", ".join(picks.get("sectors", [])) if isinstance(picks, dict) else ""
        return context

    def generate(self, article: Any) -> ArticleInsight:
        context = self.build_context(article)
        prompt = PromptManager.load("article_insight", context)
        try:
            if hasattr(self.service, "generate_insight"):
                data = self.service.generate_insight(article)
            else:
                data = self.service._chat_json(prompt, context["paragraphs"], max_tokens=1200)
            values = {field: data.get(field, [] if field != "summary" else "") for field in FIELDS}
            for field in FIELDS[1:]:
                values[field] = [str(item) for item in values[field]] if isinstance(values[field], list) else []
                values[field] = values[field][:3]
            values["summary"] = str(values["summary"])
            return ArticleInsight(**values)
        except Exception as exc:
            raise ArticleInsightError(f"Article insight generation failed: {exc}") from exc


def render_insight(insight: ArticleInsight) -> str:
    lines = ["<div class=\"article-insight\">", f"<p><strong>Summary:</strong> {insight.summary}</p>"]
    for label, values in (("Why it matters", insight.why_it_matters), ("Market impact", insight.market_impact), ("Risks", insight.risks), ("Follow-up questions", insight.follow_up_questions)):
        if values:
            lines.extend([f"<p><strong>{label}</strong></p><ul>", *[f"<li>{value}</li>" for value in values], "</ul>"])
    lines.append("</div>")
    return "\n".join(lines)
