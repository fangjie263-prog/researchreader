"""Lightweight title-based article merger."""

from __future__ import annotations

from copy import deepcopy
import re
import hashlib
from difflib import SequenceMatcher


class ArticleMerger:
    """Merge article fragments whose normalized titles are identical."""

    @staticmethod
    def _key(article: dict) -> str:
        return str(article.get("title", "")).strip().lower()

    @classmethod
    def _paragraph_text(cls, paragraph: object) -> str:
        if isinstance(paragraph, dict):
            return cls._normalize(paragraph.get("text", ""))
        return cls._normalize(paragraph)

    @classmethod
    def opening_body_hash(cls, article: dict) -> str:
        paragraphs = [cls._paragraph_text(p) for p in article.get("paragraphs", [])]
        opening = " ".join(p for p in paragraphs[:3] if p)[:800]
        return hashlib.sha256(opening.casefold().encode("utf-8")).hexdigest() if opening else ""

    @classmethod
    def fingerprint(cls, article: dict) -> str:
        body = " ".join(cls._paragraph_text(p) for p in article.get("paragraphs", []))[:300]
        identity = "|".join((cls._key(article), cls._normalize(article.get("byline", article.get("author", ""))).lower(), body))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @classmethod
    def _similar(cls, left: object, right: object) -> float:
        return SequenceMatcher(None, cls._normalize(left).lower(), cls._normalize(right).lower()).ratio()

    @classmethod
    def _same_logical_article(cls, left: dict, right: dict) -> bool:
        title_left, title_right = cls._key(left), cls._key(right)
        if title_left and title_left == title_right:
            return True
        if title_left and title_right and cls._similar(title_left, title_right) >= 0.90:
            return True
        left_hash = cls.opening_body_hash(left)
        right_hash = cls.opening_body_hash(right)
        if left_hash and left_hash == right_hash:
            left_images = {str(i.get("src", "")) for i in left.get("images", []) if isinstance(i, dict)}
            right_images = {str(i.get("src", "")) for i in right.get("images", []) if isinstance(i, dict)}
            left_annotation = cls._normalize(left.get("annotation", "")).casefold()
            right_annotation = cls._normalize(right.get("annotation", "")).casefold()
            if left_images & right_images or (left_annotation and left_annotation == right_annotation):
                return True
        author_left = cls._normalize(left.get("byline", left.get("author", ""))).lower()
        author_right = cls._normalize(right.get("byline", right.get("author", ""))).lower()
        left_body = left.get("paragraphs", [])
        right_body = right.get("paragraphs", [])
        if author_left and author_left == author_right and left_body and right_body:
            opening_left = " ".join(map(str, left_body[:2]))
            opening_right = " ".join(map(str, right_body[:2]))
            return cls._similar(opening_left, opening_right) >= 0.90
        return False

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
            key = cls._paragraph_text(paragraph)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(paragraph)
        return deduped

    @staticmethod
    def _merge_images(target: dict, article: dict) -> None:
        if "images" in target or "images" in article:
            target.setdefault("images", [])
            images = target["images"] + list(article.get("images", []))
            seen: set[str] = set()
            deduped: list = []
            for image in images:
                src = str(image.get("src", "")) if isinstance(image, dict) else ""
                if src in seen:
                    continue
                seen.add(src)
                deduped.append(image)
            target["images"] = deduped

    @classmethod
    def _remove_annotation_from_body(cls, article: dict) -> None:
        annotation = cls._normalize(article.get("annotation", "")).casefold()
        if not annotation:
            return
        article["paragraphs"] = [
            paragraph for paragraph in article.get("paragraphs", [])
            if cls._paragraph_text(paragraph).casefold() != annotation
        ]

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
        original_images = sum(len(article.get("images", [])) for article in articles)
        merged: list[dict] = []
        index_by_title: dict[str, int] = {}
        for article in articles:
            key = self._key(article)
            if key and key in index_by_title:
                target = merged[index_by_title[key]]
                self._merge_text(target, article)
                self._merge_images(target, article)
                self._remove_annotation_from_body(target)
                continue

            cloned = deepcopy(article)
            cloned.setdefault("article_id", self.fingerprint(article))
            merged.append(cloned)
            if key:
                index_by_title[key] = len(merged) - 1
            # Check nearby candidates for PressReader continuation metadata.
            for candidate_index, candidate in enumerate(merged[:-1]):
                if self._same_logical_article(candidate, cloned):
                    self._merge_text(candidate, cloned)
                    self._merge_images(candidate, cloned)
                    self._remove_annotation_from_body(candidate)
                    merged.pop()
                    if key:
                        index_by_title[key] = candidate_index
                    break

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
            images_after = sum(len(article.get("images", [])) for article in merged)
            print(f"Images before: {original_images}")
            print(f"Images after: {images_after}")
            print(f"Images removed: {original_images - images_after}")
            warnings = self.validate(merged)
            print(f"Article validation warnings: {len(warnings)}")
            for warning in warnings:
                print(f"  WARNING: {warning}")
        return merged

    @classmethod
    def validate(cls, articles: list[dict]) -> list[str]:
        warnings: list[str] = []
        titles = [cls._key(article) for article in articles if cls._key(article)]
        annotations = [cls._normalize(article.get("annotation", "")).lower() for article in articles if article.get("annotation")]
        authors = [cls._normalize(article.get("byline", article.get("author", ""))).lower() for article in articles if article.get("byline", article.get("author", ""))]
        fingerprints = [article.get("article_id", cls.fingerprint(article)) for article in articles]
        for name, values in (("title", titles), ("annotation", annotations), ("author", authors), ("fingerprint", fingerprints)):
            if len(values) != len(set(values)):
                warnings.append(f"Duplicate {name}s detected")
        return warnings
