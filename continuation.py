"""Detect explicit cross-page continuation markers without merging content."""

from __future__ import annotations

from dataclasses import dataclass
import re


MARKER_PATTERNS = [
    re.compile(r"\bcontinued\s+on\s+(?:page\s+)?(?P<ref>[a-z]\d+)\b", re.IGNORECASE),
    re.compile(r"\bcontinued\s+from\s+(?:page\s+)?(?P<ref>[a-z]\d+)\b", re.IGNORECASE),
    re.compile(r"\bsee\s+page\s+(?P<ref>[a-z]\d+)\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+page\s+(?P<ref>[a-z]\d+)\b", re.IGNORECASE),
    re.compile(r"\bpage\s+(?P<ref>[a-z]\d+)\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class ContinuationLink:
    source_article: str
    target_article: str
    page_reference: str
    marker: str


class ContinuationResolver:
    """Build article-to-article links from explicit continuation markers."""

    @staticmethod
    def _article_id(article: dict, index: int) -> str:
        article_id = str(article.get("article_id") or "").strip()
        return article_id or f"article_{index:03d}"

    @staticmethod
    def _page_reference(article: dict) -> str:
        for key in ("page_reference", "_page_reference"):
            value = str(article.get(key) or "").strip()
            if value:
                return value
        page = article.get("_page", article.get("page"))
        if page is not None and str(page).strip():
            return f"Page {str(page).strip()}"
        return ""

    @staticmethod
    def _scan_text(text: str) -> list[tuple[str, str]]:
        matches: list[tuple[str, str]] = []
        if not text:
            return matches
        for pattern in MARKER_PATTERNS:
            for match in pattern.finditer(text):
                ref = match.group("ref").strip()
                matches.append((match.group(0), ref.upper()))
        return matches

    def resolve(self, articles: list[dict], *, emit_log: bool = True) -> list[ContinuationLink]:
        page_index: dict[str, str] = {}
        article_ids = [self._article_id(article, index) for index, article in enumerate(articles, start=1)]

        for index, article in enumerate(articles, start=1):
            page_reference = self._page_reference(article)
            if page_reference:
                page_index[page_reference.strip().upper()] = article_ids[index - 1]

        links: list[ContinuationLink] = []
        seen: set[tuple[str, str, str]] = set()

        for index, article in enumerate(articles, start=1):
            source_id = article_ids[index - 1]
            parts = [
                str(article.get("title") or ""),
                str(article.get("subtitle") or ""),
            ]
            parts.extend(str(paragraph) for paragraph in article.get("paragraphs", []))
            for part in parts:
                for marker, ref in self._scan_text(part):
                    target_id = page_index.get(ref)
                    if not target_id:
                        continue
                    key = (source_id, target_id, ref)
                    if key in seen:
                        continue
                    seen.add(key)
                    links.append(
                        ContinuationLink(
                            source_article=source_id,
                            target_article=target_id,
                            page_reference=ref,
                            marker=marker,
                        )
                    )

        if emit_log:
            print("Continuation:")
            print(f"Detected links: {len(links)}")
            for link in links:
                print(f"{link.source_article} -> {link.target_article} ({link.page_reference})")

        return links


class ContinuationMerger:
    """Apply continuation links exactly once per target article."""

    @staticmethod
    def _article_id(article: dict, index: int) -> str:
        article_id = str(article.get("article_id") or "").strip()
        if article_id:
            return article_id
        generated = f"article_{index:03d}"
        article["article_id"] = generated
        return generated

    @staticmethod
    def _ensure_guard(article: dict) -> set[str]:
        guard = article.get("merged_article_ids")
        if isinstance(guard, set):
            return guard
        if isinstance(guard, list):
            guard = set(guard)
        else:
            guard = set()
        article["merged_article_ids"] = guard
        return guard

    @staticmethod
    def _append_unique(target: dict, source: dict) -> tuple[int, int]:
        before = len(target.get("paragraphs", []) or [])
        target.setdefault("paragraphs", [])
        target.setdefault("images", [])
        target["paragraphs"].extend(source.get("paragraphs", []))
        target["images"].extend(source.get("images", []))
        after = len(target.get("paragraphs", []) or [])
        return before, after

    def merge(self, articles: list[dict], links: list[ContinuationLink], *, emit_log: bool = True) -> list[dict]:
        if not articles or not links:
            return articles

        article_ids = [self._article_id(article, index) for index, article in enumerate(articles, start=1)]
        by_id = {article_id: article for article_id, article in zip(article_ids, articles)}
        attempts = merged = skipped = 0

        for link in links:
            source = by_id.get(link.source_article)
            target = by_id.get(link.target_article)
            if source is None or target is None:
                continue
            attempts += 1
            guard = self._ensure_guard(target)
            if link.source_article in guard:
                skipped += 1
                if emit_log:
                    print("Merge Audit")
                    print(f"Source:\n{link.source_article}")
                    print(f"Target:\n{link.target_article}")
                    print("Status:\nSKIPPED")
                    print("Reason:\nAlready merged.")
                continue

            before, after = self._append_unique(target, source)
            guard.add(link.source_article)
            merged += 1
            if emit_log:
                print("Merge Audit")
                print(f"Source:\n{link.source_article}")
                print(f"Target:\n{link.target_article}")
                print(f"Paragraphs before:\n{before}")
                print(f"Paragraphs appended:\n{len(source.get('paragraphs', []) or [])}")
                print(f"Paragraphs after:\n{after}")

        if emit_log:
            print("Continuation Merge Summary")
            print(f"Merge attempts:\n{attempts}")
            print(f"Merged:\n{merged}")
            print(f"Skipped:\n{skipped}")

        return articles
