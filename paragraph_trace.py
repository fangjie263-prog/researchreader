"""Trace repeated paragraphs inside parsed articles without changing parsing."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
DEFAULT_JSON = OUTPUT_DIR / "paragraph_trace.json"


def _normalize(paragraph: str) -> str:
    return re.sub(r"\s+", " ", str(paragraph).replace("\r\n", "\n").replace("\r", "\n")).strip()


def _hash(paragraph: str) -> str:
    return hashlib.sha1(_normalize(paragraph).encode("utf-8")).hexdigest()


class ParagraphTracer:
    def trace(self, articles: list[dict], output_path: str | Path | None = None) -> dict:
        report: list[dict] = []
        duplicate_articles = 0
        duplicate_total = 0

        for index, article in enumerate(articles, start=1):
            paragraphs = [str(paragraph) for paragraph in article.get("paragraphs", []) or []]
            hashes: dict[str, dict] = {}
            duplicates: list[dict] = []
            for position, paragraph in enumerate(paragraphs, start=1):
                digest = _hash(paragraph)
                bucket = hashes.setdefault(digest, {"first_index": position, "duplicate_indexes": []})
                if bucket["first_index"] != position:
                    bucket["duplicate_indexes"].append(position)
                    duplicate_total += 1
                else:
                    bucket["first_index"] = position

            unique_count = len(hashes)
            if any(item["duplicate_indexes"] for item in hashes.values()):
                duplicate_articles += 1
            for digest, info in hashes.items():
                if info["duplicate_indexes"]:
                    duplicates.append({
                        "hash": digest,
                        "first_index": info["first_index"],
                        "duplicate_indexes": info["duplicate_indexes"],
                    })

            report.append({
                "article_id": article.get("article_id") or f"article_{index:03d}",
                "title": str(article.get("title") or "(No title)"),
                "paragraphs": len(paragraphs),
                "unique": unique_count,
                "duplicates": duplicates,
                "source_file": article.get("_source") or article.get("source_file") or "",
                "paragraph_source_metadata": "Current parser does not retain paragraph source metadata.",
            })

        summary = {
            "articles": len(articles),
            "articles_with_duplicate_paragraphs": duplicate_articles,
            "duplicate_paragraph_count": duplicate_total,
        }
        payload = {"summary": summary, "articles": report}
        target = Path(output_path) if output_path else DEFAULT_JSON
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def print_summary(self, report: dict) -> None:
        summary = report["summary"]
        print("Paragraph Trace")
        print(f"Articles: {summary['articles']}")
        print(f"Articles with duplicate paragraphs: {summary['articles_with_duplicate_paragraphs']}")
        print(f"Duplicate paragraph count: {summary['duplicate_paragraph_count']}")


def load_articles(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "articles" in data:
        return list(data["articles"])
    if isinstance(data, list):
        return list(data)
    raise ValueError("Unsupported paragraph trace input format")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace repeated paragraphs in parser output.")
    parser.add_argument("source", nargs="?", help="Optional JSON file with articles.")
    args = parser.parse_args()
    if not args.source:
        raise SystemExit("Please provide a JSON file path for paragraph_trace.py")
    report = ParagraphTracer().trace(load_articles(Path(args.source)))
    ParagraphTracer().print_summary(report)


if __name__ == "__main__":
    main()
