"""Centralized, conservative cleanup for parsed article dictionaries."""
from __future__ import annotations

import copy
import re
from collections import Counter

from cleaner_rules import EMAIL_PATTERN, NOISE_PATTERNS, SECTION_HEADING_EXCLUSIONS, SECTION_HEADING_RULES


class ArticleCleaner:
    def __init__(self):
        self.audit = Counter()

    def clean(self, article: dict) -> dict:
        result = copy.deepcopy(article)
        self.audit["articles"] += 1
        paragraphs = []
        for paragraph in result.get("paragraphs", []):
            text = str(paragraph).strip()
            if text.startswith("[Image:"):
                self.audit["captions_recovered"] += 1
            if self._is_noise(text):
                self.audit["noise_removed"] += 1
                continue
            if re.fullmatch(EMAIL_PATTERN, text, re.IGNORECASE) or text.lower().startswith("email:"):
                self.audit["email_lines_removed"] += 1
                continue
            if re.search(EMAIL_PATTERN, text):
                text = re.sub(EMAIL_PATTERN, "", text).strip()
                text = re.sub(r"\s+", " ", text)
                self.audit["email_lines_removed"] += 1
                if not text:
                    continue
            if self._is_heading(text, paragraphs, result.get("paragraphs", [])):
                paragraphs.append({"text": text, "type": "section_heading"})
                self.audit["section_headings"] += 1
            else:
                paragraphs.append(text)
        result["paragraphs"] = paragraphs
        self._clean_metadata(result)
        return result

    def _is_noise(self, text: str) -> bool:
        return any(re.fullmatch(pattern, text, re.IGNORECASE) for pattern in NOISE_PATTERNS)

    def _is_heading(self, text: str, previous: list, original: list) -> bool:
        rules = SECTION_HEADING_RULES
        if text.casefold() in SECTION_HEADING_EXCLUSIONS:
            return False
        if not (rules["min_length"] <= len(text) <= rules["max_length"]):
            return False
        if len(text.split()) > rules["max_words"] or re.search(r"[.!?]$", text):
            return False
        index = len(previous)
        return 0 < index < len(original) - 1

    def _clean_metadata(self, article: dict) -> None:
        subtitle = str(article.get("subtitle", "")).strip()
        title = str(article.get("title", "")).strip()
        if subtitle and (len(subtitle) > len(title) or re.search(r"[.:?!]", subtitle)):
            article["subtitle"] = ""
            self.audit["toc_titles_corrected"] += 1
        byline = str(article.get("byline", ""))
        article["byline"] = re.sub(EMAIL_PATTERN, "", byline, flags=re.IGNORECASE).strip()

    def clean_articles(self, articles: list[dict]) -> list[dict]:
        self.audit.clear()
        cleaned = [self.clean(article) for article in articles]
        print("Cleaner Audit")
        print(f"Articles processed: {self.audit['articles']}")
        print(f"Paragraphs removed: {self.audit['noise_removed'] + self.audit['email_lines_removed']}")
        print(f"Section headings detected: {self.audit['section_headings']}")
        print(f"Noise removed: {self.audit['noise_removed']}")
        print(f"Captions recovered: {self.audit['captions_recovered']}")
        print(f"TOC titles corrected: {self.audit['toc_titles_corrected']}")
        return cleaned
