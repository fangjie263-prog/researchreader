"""Lightweight title-based article merger."""

from __future__ import annotations

from copy import deepcopy
import re


class ArticleMerger:
    """Merge article fragments whose normalized titles are identical."""

    @staticmethod
    def _key(article: dict) -> str:
        return str(article.get("title", "")).strip().lower()

    @staticmethod
    def _merge_text(target: dict, article: dict) -> None:
        if "content" in target or "content" in article:
            left = str(target.get("content", "")).strip()
            right = str(article.get("content", "")).strip()
            if left and right:
                target["content"] = f"{left}\n\n{right}"
            elif right:
                target["content"] = right
            return

        if "paragraphs" in target or "paragraphs" in article:
            target.setdefault("paragraphs", [])
            target["paragraphs"] = ArticleMerger._smart_merge_paragraphs(
                target["paragraphs"], article.get("paragraphs", [])
            )

    @staticmethod
    def _normalize(text: object) -> str:
        return re.sub(r"\s+", " ", str(text).replace("\r\n", "\n").replace("\r", "\n")).strip()

    @classmethod
    def _join_overlap(cls, left: str, right: str) -> str | None:
        """Join two boundary fragments using their longest exact overlap."""
        left_key = cls._normalize(left)
        right_key = cls._normalize(right)
        limit = min(len(left_key), len(right_key))
        for size in range(limit, 0, -1):
            if left_key[-size:] == right_key[:size]:
                return left_key + right_key[size:]
        return None

    @classmethod
    def _smart_merge_paragraphs(cls, left: list, right: list) -> list:
        result = list(left)
        incoming = list(right)
        if result and incoming:
            joined = cls._join_overlap(str(result[-1]), str(incoming[0]))
            if joined is not None:
                result[-1] = joined
                incoming.pop(0)

            # A whole paragraph may already be the suffix of the target.
            max_overlap = min(len(result), len(incoming))
            overlap = 0
            for size in range(max_overlap, 0, -1):
                if all(cls._normalize(result[-size + i]) == cls._normalize(incoming[i]) for i in range(size)):
                    overlap = size
                    break
            if overlap:
                incoming = incoming[overlap:]
        result.extend(incoming)

        deduped: list = []
        seen: set[str] = set()
        for paragraph in result:
            key = cls._normalize(paragraph)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(paragraph)
        return deduped

    @staticmethod
    def _merge_images(target: dict, article: dict) -> None:
        if "images" in target or "images" in article:
            target.setdefault("images", [])
            target["images"].extend(article.get("images", []))

    def merge(self, articles: list[dict], *, emit_log: bool = True) -> list[dict]:
        if not articles:
            if emit_log:
                print("Article merge:")
                print("Before: 0")
                print("After : 0")
                print("Merged: 0 duplicate titles")
            return []

        before = len(articles)
        original_paragraphs = sum(len(article.get("paragraphs", [])) for article in articles)
        merged: list[dict] = []
        index_by_title: dict[str, int] = {}
        for article in articles:
            key = self._key(article)
            if key and key in index_by_title:
                target = merged[index_by_title[key]]
                self._merge_text(target, article)
                self._merge_images(target, article)
                continue

            cloned = deepcopy(article)
            merged.append(cloned)
            if key:
                index_by_title[key] = len(merged) - 1

        if emit_log:
            print("Article merge:")
            print(f"Before: {before}")
            print(f"After : {len(merged)}")
            print(f"Merged: {before - len(merged)} duplicate titles")
            after_overlap = sum(len(article.get("paragraphs", [])) for article in merged)
            print("Merge Audit")
            print(f"Original paragraphs: {original_paragraphs}")
            print(f"After overlap merge: {after_overlap}")
            print(f"After deduplication: {after_overlap}")
            print(f"Removed duplicates: {original_paragraphs - after_overlap}")
        return merged
