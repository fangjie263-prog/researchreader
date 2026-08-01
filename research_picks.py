"""Deterministic, post-parser investment reading picks."""
from __future__ import annotations

import json
import re
from pathlib import Path


COMPANIES = ("Apple", "Microsoft", "Amazon", "Chevron", "Exxon", "NVIDIA", "OpenAI", "Anthropic", "TSMC", "Google", "Meta")
SECTORS = {
    "AI": ("AI", "artificial intelligence", "OpenAI", "Anthropic", "ChatGPT"),
    "Semiconductor": ("semiconductor", "GPU", "chip", "NVIDIA", "TSMC"),
    "Energy": ("oil", "energy", "Chevron", "Exxon", "natural gas"),
    "Healthcare": ("healthcare", "health", "drug", "pharma"),
    "Defense": ("defense", "military", "weapons"),
    "Macro": ("inflation", "interest rates", "Federal Reserve", "Fed", "GDP"),
    "Consumer": ("consumer", "retail", "shopping"),
}


def _text(article: dict) -> str:
    parts = [str(article.get("title", "")), str(article.get("subtitle", "")), str(article.get("annotation", ""))]
    parts.extend(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in article.get("paragraphs", []))
    return " ".join(parts)


class ResearchPicks:
    def enrich(self, articles: list[dict]) -> list[dict]:
        for article in articles:
            text = _text(article)
            score = max(0, min(100, int(article.get("local_score", 0) or 0)))
            stars = min(5, max(1, (score + 19) // 20))
            companies = [name for name in COMPANIES if re.search(rf"\b{re.escape(name)}\b", text, re.I)]
            sectors = [name for name, terms in SECTORS.items() if any(term.casefold() in text.casefold() for term in terms)]
            article["research_picks"] = {
                "rating": "★" * stars + "☆" * (5 - stars),
                "importance_score": score,
                "why_it_matters": [f"涉及{', '.join(sectors[:3]) or '重点研究主题'}。"],
                "market_impact": [f"关注{', '.join(companies[:3]) or '相关行业'}后续变化。"],
                "companies": companies,
                "sectors": sectors,
                "macro_tags": article.get("matched_topics", []),
                "estimated_read_time": f"{max(1, round(len(article.get('paragraphs', [])) * 45 / 200))} min",
            }
        return articles

    def write_candidates(self, articles: list[dict], path: str | Path) -> Path:
        records = []
        for article in articles:
            record = {key: article.get(key, []) for key in ("title", "source", "local_score", "matched_keywords", "matched_topics", "preview")}
            record["research_picks"] = article.get("research_picks", {})
            records.append(record)
        output = Path(path)
        output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        return output
