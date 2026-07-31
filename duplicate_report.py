"""Report residual exact duplicate paragraphs without changing article data."""

from __future__ import annotations

import json
import re
from pathlib import Path


def normalize(text: object) -> str:
    return re.sub(r"\s+", " ", str(text).replace("\r\n", "\n").replace("\r", "\n")).strip()


def build_report(articles: list[dict]) -> list[dict]:
    report = []
    for article in articles:
        positions: dict[str, list[int]] = {}
        values: dict[str, str] = {}
        for index, paragraph in enumerate(article.get("paragraphs", [])):
            key = normalize(paragraph)
            if not key:
                continue
            positions.setdefault(key, []).append(index)
            values.setdefault(key, str(paragraph))
        for key, occurrences in positions.items():
            if len(occurrences) > 1:
                report.append({
                    "article_id": article.get("article_id", ""),
                    "title": article.get("title", ""),
                    "duplicate_text": values[key],
                    "occurrences": occurrences,
                })
    return report


def write_report(articles: list[dict], output: str | Path = "output/duplicate_report.json") -> list[dict]:
    report = build_report(articles)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Residual Duplicate Report")
    for item in report:
        print(f"Article: {item['title']}")
        print(f"Paragraph: {item['duplicate_text']}")
        print("Occurrences: " + ",".join(map(str, item["occurrences"])))
    return report


if __name__ == "__main__":
    from wsj_reader import read_epub

    books = sorted(Path("books").glob("*.epub"))
    if not books:
        raise SystemExit("No EPUB file found in books/")
    write_report(read_epub(str(books[0]))[2])
