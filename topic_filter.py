"""Pure local topic filtering for ResearchReader articles."""

from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
import html
import json
import re
from pathlib import Path
from typing import Any

from topic_manager import ALIASES_PATH, load_topic_records


ROOT = Path(__file__).resolve().parent
DEFAULT_TOPICS_PATH = ROOT / "config" / "topics.json"
DEFAULT_ALIASES_PATH = ALIASES_PATH
DEFAULT_THRESHOLD = 15
NEGATIVE_KEYWORDS = [
    "Sports",
    "Golf",
    "Crossword",
    "Sudoku",
    "Travel",
    "Opinion",
    "Fashion",
    "Arts",
    "Books",
    "Life",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _count_occurrences(text: str, term: str) -> int:
    if not text or not term:
        return 0
    pattern = re.escape(_normalize(term))
    if not pattern:
        return 0
    return len(re.findall(pattern, _normalize(text)))


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            result.append(value.strip())
    return result


def _article_text(article: dict[str, Any]) -> tuple[str, str, str]:
    title = str(article.get("title", "") or "").strip()
    subtitle = str(article.get("subtitle", "") or article.get("annotation", "") or "").strip()
    body_parts: list[str] = []
    paragraphs = article.get("paragraphs")
    if isinstance(paragraphs, list):
        body_parts.extend(str(item).strip() for item in paragraphs if str(item).strip())
    for key in ("content", "text", "body"):
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            body_parts.append(value.strip())
    body = "\n".join(body_parts).strip()
    return title, subtitle, body


def _highlight(text: str, keywords: list[str]) -> str:
    result = text
    for keyword in sorted({item for item in keywords if item}, key=len, reverse=True):
        escaped = re.escape(keyword)
        result = re.sub(escaped, lambda match: f"**{match.group(0)}**", result, flags=re.IGNORECASE)
    return result


@dataclass
class TopicFilterStats:
    scanned: int = 0
    selected: int = 0
    total_score: float = 0.0
    keyword_counts: Counter[str] | None = None

    def __post_init__(self) -> None:
        if self.keyword_counts is None:
            self.keyword_counts = Counter()

    @property
    def ratio(self) -> float:
        if not self.scanned:
            return 0.0
        return self.selected / self.scanned

    @property
    def average_score(self) -> float:
        if not self.selected:
            return 0.0
        return self.total_score / self.selected


class TopicFilter:
    """Score articles locally and keep only topic-relevant candidates."""

    def __init__(
        self,
        topics_path: Path | str = DEFAULT_TOPICS_PATH,
        aliases_path: Path | str = DEFAULT_ALIASES_PATH,
        threshold: int = DEFAULT_THRESHOLD,
    ) -> None:
        self.topics_path = Path(topics_path)
        self.aliases_path = Path(aliases_path)
        self.threshold = threshold
        self.topics = self._load_topics()
        self.stats = TopicFilterStats()
        self._keyword_to_topics = self._build_keyword_index()

    def _load_topics(self) -> list[dict[str, Any]]:
        return load_topic_records(self.topics_path, self.aliases_path)

    def _build_keyword_index(self) -> dict[str, list[dict[str, str]]]:
        index: dict[str, list[dict[str, str]]] = {}
        for topic in self.topics:
            if not isinstance(topic, dict):
                continue
            name = str(topic.get("name_zh", "") or "").strip()
            primary_terms = [name] + _clean_list(topic.get("keywords_zh")) + _clean_list(topic.get("keywords_en"))
            related_terms = _clean_list(topic.get("related_topics"))
            for term in primary_terms:
                index.setdefault(_normalize(term), []).append({"topic": name, "kind": "primary"})
            for term in related_terms:
                index.setdefault(_normalize(term), []).append({"topic": name, "kind": "related"})
        return index

    def _score_field(
        self,
        field_name: str,
        field_text: str,
        term: str,
        related: bool = False,
    ) -> int:
        count = _count_occurrences(field_text, term)
        if not count:
            return 0
        if related:
            return 3 + max(0, count - 1)
        weights = {"title": 20, "subtitle": 10, "body": 5}
        return weights.get(field_name, 0) + max(0, count - 1)

    def _score_article(self, article: dict[str, Any], index: int) -> tuple[int, list[str], list[str], str]:
        title, subtitle, body = _article_text(article)
        fields = {"title": title, "subtitle": subtitle, "body": body}
        matched_keywords: "OrderedDict[str, None]" = OrderedDict()
        matched_topics: "OrderedDict[str, None]" = OrderedDict()
        score = 0

        for topic in self.topics:
            if not isinstance(topic, dict):
                continue
            topic_name = str(topic.get("name_zh", "") or "").strip()
            primary_terms = [topic_name] + _clean_list(topic.get("keywords_zh")) + _clean_list(topic.get("keywords_en"))
            related_terms = _clean_list(topic.get("related_topics"))
            topic_hit = False
            for term in primary_terms:
                term_norm = _normalize(term)
                if not term_norm:
                    continue
                term_score = 0
                for field_name, field_text in fields.items():
                    term_score += self._score_field(field_name, field_text, term, related=False)
                if term_score:
                    score += term_score
                    matched_keywords.setdefault(term, None)
                    topic_hit = True
            for term in related_terms:
                term_score = 0
                for field_name, field_text in fields.items():
                    term_score += self._score_field(field_name, field_text, term, related=True)
                if term_score:
                    score += term_score
                    matched_keywords.setdefault(term, None)
                    topic_hit = True
            if topic_hit and topic_name:
                matched_topics.setdefault(topic_name, None)

        haystack = _normalize("\n".join(part for part in fields.values() if part))
        for keyword in NEGATIVE_KEYWORDS:
            if _normalize(keyword) and _normalize(keyword) in haystack:
                score -= 30

        preview = body or subtitle or title
        preview = preview.replace("\n", " ").strip()
        if len(preview) > 320:
            preview = preview[:317].rstrip() + "..."
        preview = _highlight(preview, list(matched_keywords))

        article["local_score"] = score
        article["matched_keywords"] = list(matched_keywords.keys())
        article["matched_topics"] = list(matched_topics.keys())
        article["preview"] = preview
        article["source_index"] = index
        return score, list(matched_keywords.keys()), list(matched_topics.keys()), preview

    def filter_articles(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach local scores to articles and return the ones above threshold."""
        self.stats = TopicFilterStats(scanned=len(articles))
        scored: list[tuple[int, int, dict[str, Any]]] = []

        for index, article in enumerate(articles):
            if not isinstance(article, dict):
                continue
            score, keywords, _, _ = self._score_article(article, index)
            if score > self.threshold:
                scored.append((score, index, article))
                self.stats.selected += 1
                self.stats.total_score += score
                for keyword in keywords:
                    self.stats.keyword_counts[keyword] += 1

        scored.sort(key=lambda item: (-item[0], item[1]))
        return [article for _, _, article in scored]

    def write_reports(self, articles: list[dict[str, Any]], output_dir: Path | str) -> tuple[Path, Path]:
        """Write candidate_articles.json and candidate_articles.md."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "candidate_articles.json"
        md_path = output_dir / "candidate_articles.md"

        records: list[dict[str, Any]] = []
        for article in articles:
            records.append({
                "title": article.get("title", ""),
                "source": article.get("source", article.get("source_document", article.get("_source", ""))),
                "score": article.get("local_score", 0),
                "matched_keywords": article.get("matched_keywords", []),
                "preview": article.get("preview", ""),
                "matched_topics": article.get("matched_topics", []),
                "research_picks": article.get("research_picks", {}),
            })

        json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

        lines = ["# Candidate Articles", ""]
        lines.extend([
            f"Articles scanned: {self.stats.scanned}",
            f"Articles selected: {self.stats.selected}",
            f"Selection ratio: {self.stats.ratio:.1%}",
            f"Average score: {self.stats.average_score:.1f}",
            "",
        ])
        if self.stats.keyword_counts:
            top_keywords = ", ".join(
                f"{keyword} ({count})"
                for keyword, count in self.stats.keyword_counts.most_common(20)
            )
            lines.append(f"Top 20 keywords: {top_keywords}")
            lines.append("")
        for index, article in enumerate(articles, start=1):
            keywords = article.get("matched_keywords", [])
            source = article.get("source", article.get("source_document", article.get("_source", "")))
            lines.extend([
                f"## {index}. {article.get('title', '')}",
                f"- Source: `{source}`",
                f"- Score: {article.get('local_score', 0)}",
                f"- Matched Keywords: {', '.join(f'**{keyword}**' for keyword in keywords) or 'None'}",
                f"- Preview: {article.get('preview', '')}",
                "",
            ])
        md_path.write_text("\n".join(lines), encoding="utf-8")
        return json_path, md_path

    def print_stats(self) -> None:
        """Print a short local-filter summary."""
        print("---------------------------------")
        print(f"Articles scanned : {self.stats.scanned}")
        print(f"Articles selected : {self.stats.selected}")
        print(f"Selection ratio : {self.stats.ratio:.1%}")
        print(f"Average score : {self.stats.average_score:.1f}")
        if self.stats.keyword_counts:
            top = ", ".join(
                f"{keyword} ({count})" for keyword, count in self.stats.keyword_counts.most_common(20)
            )
            print(f"Top 20 keywords : {top}")
        print("---------------------------------")
