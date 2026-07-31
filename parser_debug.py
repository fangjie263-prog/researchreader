"""Parser debugging helpers for visualizing article segmentation."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
DEFAULT_JSON = OUTPUT_DIR / "parser_debug.json"


def _first_text(article: dict) -> str:
    for text in article.get("paragraphs", []) or []:
        text = str(text).strip()
        if text:
            return text
    return ""


def _last_text(article: dict) -> str:
    for text in reversed(article.get("paragraphs", []) or []):
        text = str(text).strip()
        if text:
            return text
    return ""


def _sentence(text: str, first: bool) -> str:
    chunks = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
    if not chunks:
        return ""
    return chunks[0] if first else chunks[-1]


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a_tokens = {token for token in re.findall(r"[A-Za-z0-9]+", a.lower()) if len(token) > 2}
    b_tokens = {token for token in re.findall(r"[A-Za-z0-9]+", b.lower()) if len(token) > 2}
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens) / max(1, min(len(a_tokens), len(b_tokens)))
    return overlap >= 0.5


@dataclass
class ParserDebugArticle:
    article_id: str
    title: str
    pages: int
    paragraphs: int
    images: int
    author: str
    subtitle: str
    first_paragraph: str
    last_paragraph: str
    warnings: list[str]
    info: list[str]


class ParserDebugger:
    def analyze(self, articles: list[dict]) -> dict:
        seen_titles: set[str] = set()
        duplicate_titles = 0
        untitled = 0
        possible_continuations = 0
        report: list[ParserDebugArticle] = []

        for index, article in enumerate(articles, start=1):
            article_id = str(article.get("article_id") or f"article_{index:03d}")
            title = str(article.get("title") or "").strip()
            subtitle = str(article.get("subtitle") or "").strip()
            author = str(article.get("byline") or article.get("author") or "").strip()
            paragraphs = list(article.get("paragraphs", []) or [])
            images = list(article.get("images", []) or [])
            pages = len({str(v).strip() for v in (article.get("_page"), article.get("page")) if v not in (None, "")}) or 1

            warnings: list[str] = []
            info: list[str] = []
            if not title:
                untitled += 1
                warnings.append("Article without title.")
            if paragraphs == []:
                warnings.append("Article without body.")
            if len(paragraphs) == 1:
                info.append("Single-paragraph article.")
            if len(paragraphs) > 100:
                info.append("Very long article.")
            if title:
                key = title.casefold()
                if key in seen_titles:
                    duplicate_titles += 1
                    warnings.append("Duplicate title.")
                else:
                    seen_titles.add(key)

            first_paragraph = _first_text(article)
            last_paragraph = _last_text(article)
            if index > 1:
                previous = articles[index - 2]
                if _similar(_last_text(previous), first_paragraph):
                    possible_continuations += 1
                    info.append("Possible continuation.")

            report.append(ParserDebugArticle(
                article_id=article_id,
                title=title or "(No title)",
                pages=pages,
                paragraphs=len(paragraphs),
                images=len(images),
                author=author,
                subtitle=subtitle,
                first_paragraph=first_paragraph,
                last_paragraph=last_paragraph,
                warnings=warnings,
                info=info,
            ))

        summary = {
            "articles": len(articles),
            "duplicate_titles": duplicate_titles,
            "untitled": untitled,
            "possible_continuations": possible_continuations,
        }
        return {
            "summary": summary,
            "articles": [asdict(item) for item in report],
        }

    def dump(self, articles: list[dict], output_path: str | Path | None = None) -> dict:
        report = self.analyze(articles)
        target = Path(output_path) if output_path else DEFAULT_JSON
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.print_summary(report)
        return report

    def print_summary(self, report: dict) -> None:
        summary = report["summary"]
        print("Parser Debug")
        print(f"Articles: {summary['articles']}")
        print(f"Duplicate titles: {summary['duplicate_titles']}")
        print(f"Untitled: {summary['untitled']}")
        print(f"Possible continuations: {summary['possible_continuations']}")


def load_articles(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "articles" in data:
        return list(data["articles"])
    if isinstance(data, list):
        return list(data)
    raise ValueError("Unsupported parser debug input format")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect parser output and write debug diagnostics.")
    parser.add_argument("source", nargs="?", help="Optional JSON file with article objects.")
    args = parser.parse_args()
    if args.source:
        articles = load_articles(Path(args.source))
    else:
        raise SystemExit("Please provide a JSON file path for parser_debug.py")
    ParserDebugger().dump(articles)


if __name__ == "__main__":
    main()
