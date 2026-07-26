"""Extract article text from the source document named by ArticleLocator."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from article_locator import ArticleLocator, ArticleNotFound


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE_ROOT = ROOT / "output"


class ArticleExtractionError(RuntimeError):
    """Raised when an article source cannot provide non-empty article text."""


@dataclass
class ArticleContent:
    article_id: str
    title: str
    source_document: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._ignored += 1
        elif self._ignored == 0 and tag.lower() in {"p", "br", "div", "section", "article", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._ignored:
            self._ignored -= 1
        elif self._ignored == 0 and tag.lower() in {"p", "div", "section", "article", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored == 0 and data.strip():
            self.parts.append(data)


def _clean_text(parts: list[str]) -> str:
    lines = [" ".join(line.split()) for line in "".join(parts).splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_markdown(text: str, title: str) -> str:
    sections: list[tuple[str, list[str]]] = []
    current_title = ""
    current_body: list[str] = []
    for line in text.splitlines():
        heading = line.strip()
        if heading.startswith("#"):
            if current_body:
                sections.append((current_title, current_body))
            current_title = heading.lstrip("#").strip()
            current_body = []
        elif line.strip() and not set(line.strip()) <= set("-*_ "):
            current_body.append(line.strip())
    if current_body:
        sections.append((current_title, current_body))

    matching = [body for section_title, body in sections if section_title == title]
    if matching:
        return _clean_text([line for body in matching for line in body])
    return ""


class ArticleExtractor:
    def __init__(
        self,
        locator: ArticleLocator | None = None,
        source_root: Path | str = DEFAULT_SOURCE_ROOT,
    ) -> None:
        self.locator = locator or ArticleLocator()
        self.source_root = Path(source_root)

    def extract(self, article_id: str) -> ArticleContent:
        article = self.locator.get(article_id)
        source_document = article["source_document"]
        source_path = Path(source_document)
        if not source_path.is_absolute():
            source_path = self.source_root / source_path
        if not source_path.is_file():
            raise ArticleExtractionError(f"Article source not found: {source_document}")

        suffix = source_path.suffix.lower()
        if suffix not in {".md", ".html", ".htm"}:
            raise ArticleExtractionError(f"Unsupported article source format: {source_document}")
        text = source_path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".md":
            content = _extract_markdown(text, article["title"])
        else:
            parser = _VisibleTextParser()
            parser.feed(text)
            content = _clean_text(parser.parts)
        if not content:
            raise ArticleExtractionError(f"Article body is empty: {article_id}")
        return ArticleContent(
            article_id=article_id,
            title=article["title"],
            source_document=source_document,
            content=content,
            metadata={"source_path": str(source_path)},
        )
