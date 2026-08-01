"""Canonical article data model for future pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any


@dataclass
class Article:
    uuid: str = ""
    title: str = ""
    subtitle: str = ""
    author: str = ""
    source: str = ""
    paragraphs: list[Any] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    language: str = "unknown"
    publication: str | None = None
    source_type: str = "epub"
    quality_score: int = 100
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.uuid:
            identity = "|".join((self.publication or "", self.title, self.author, self.source))
            self.uuid = hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @property
    def article_id(self) -> str:
        return str(self.metadata.get("article_id", self.uuid))

    @property
    def source_document(self) -> str:
        return self.source

    @property
    def content(self) -> str:
        return "\n".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in self.paragraphs)

    def get_dict(self) -> dict[str, Any]:
        from article_factory import ArticleFactory
        return ArticleFactory.to_dict(self)

    def __getitem__(self, key: str) -> Any:
        return self.get_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.get_dict().get(key, default)


@dataclass
class ResearchNote:
    summary: str = ""
    investment_takeaway: str = ""
    market_impact: str = "Neutral"
    companies: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    sectors: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    confidence: str = "Unknown"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchNote":
        return cls(
            summary=str(data.get("summary", "")),
            investment_takeaway=str(data.get("investment_takeaway", "")),
            market_impact=str(data.get("market_impact", "Neutral")),
            companies=list(data.get("companies", [])), industries=list(data.get("industries", data.get("sectors", []))),
            sectors=list(data.get("sectors", data.get("industries", []))), countries=list(data.get("countries", [])),
            risks=list(data.get("risks", [])), opportunities=list(data.get("opportunities", [])),
            follow_up_questions=list(data.get("follow_up_questions", data.get("questions", []))),
            confidence=str(data.get("confidence", "Unknown")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary, "investment_takeaway": self.investment_takeaway,
            "market_impact": self.market_impact, "companies": self.companies,
            "industries": self.industries, "sectors": self.sectors, "countries": self.countries,
            "risks": self.risks, "opportunities": self.opportunities,
            "follow_up_questions": self.follow_up_questions, "questions": self.follow_up_questions,
            "confidence": self.confidence,
        }


@dataclass
class AIQualityReport:
    task: str
    provider: str = "unknown"
    model: str = "unknown"
    prompt_name: str = ""
    prompt_version: str = ""
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    success: bool = False
    warnings: list[str] = field(default_factory=list)
    score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task, "provider": self.provider, "model": self.model,
            "prompt": self.prompt_name, "version": self.prompt_version,
            "latency_ms": self.latency_ms, "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens, "total_tokens": self.total_tokens,
            "success": self.success, "warnings": list(self.warnings), "score": self.score,
        }


@dataclass
class ArticleInsight:
    summary: str = ""
    why_it_matters: list[str] = field(default_factory=list)
    market_impact: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
