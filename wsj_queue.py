"""Sequential EPUB translation queue used by run_wsj.bat."""

from __future__ import annotations

import json
import os
import re
import time
import zipfile
from pathlib import Path

import wsj_reader
from ai_config import AIServiceConfig
from ai_service import AIService, AIServiceError
from continuation import ContinuationMerger, ContinuationResolver
from paragraph_trace import ParagraphTracer
from parser_debug import ParserDebugger
from topic_filter import TopicFilter
from topic_manager import topic_context


ROOT = Path(__file__).resolve().parent
BOOKS_DIR = ROOT / "books"
OUTPUT_ROOT = ROOT / "output"
DELAY_SECONDS = float(os.environ.get("WSJ_API_DELAY", "3"))
RETRIES = int(os.environ.get("WSJ_API_RETRIES", "3"))
ANALYZE = os.environ.get("WSJ_ANALYZE", "0") != "0"
TRANSLATE = os.environ.get("WSJ_TRANSLATE", "0") != "0"


def _safe_name(path: Path) -> str:
    name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", path.stem).strip("._")
    return name or "book"


def find_books() -> list[Path]:
    return sorted(BOOKS_DIR.glob("*.epub"), key=lambda p: p.name.casefold())


def validate_epub(path: Path) -> str | None:
    """Return a readable error instead of letting a corrupt EPUB abort the queue."""
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                return f"CRC check failed: {bad}"
    except (OSError, zipfile.BadZipFile) as exc:
        return f"EPUB/ZIP unreadable: {exc}"
    return None


def _progress_path(book_output: Path) -> Path:
    return book_output / "translation_progress.json"


def _load_progress(path: Path, book: Path, count: int) -> dict:
    if not path.exists():
        return {"source": book.name, "size": book.stat().st_size, "translations": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("source") == book.name and data.get("size") == book.stat().st_size:
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"source": book.name, "size": book.stat().st_size, "translations": {}}


def _save_progress(path: Path, data: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _translate_with_retry(service: AIService, article: dict, book_name: str, index: int) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            translated = service.translate_article(article)
            if not isinstance(translated.get("paragraphs"), list):
                raise AIServiceError("paragraphs is not an array")
            return translated
        except (AIServiceError, OSError, ValueError) as exc:
            last_error = exc
            if attempt < RETRIES:
                wait = max(DELAY_SECONDS, 2 ** (attempt - 1) * 5)
                print(f"    {book_name} article {index} failed, retrying in {wait:.0f}s ({attempt}/{RETRIES})")
                time.sleep(wait)
    raise AIServiceError(f"article {index} translation failed: {last_error}")


def _analyze_article(service: AIService, article: dict) -> dict | None:
    parts = [article.get("title", ""), article.get("subtitle", ""), article.get("annotation", "")]
    parts.extend(article.get("paragraphs", [])[:10])
    text = "\n\n".join(part for part in parts if part)
    if not text.strip():
        return None
    try:
        return json.loads(service.summarize(text, topic_context=topic_context()))
    except (AIServiceError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"    AI analysis skipped: {exc}")
        return None


def process_book(book: Path, service: AIService | None) -> bool:
    book_output = OUTPUT_ROOT / _safe_name(book)
    book_output.mkdir(parents=True, exist_ok=True)
    error = validate_epub(book)
    if error:
        print(f"  SKIP: {error}")
        (book_output / "ERROR.txt").write_text(error + "\n", encoding="utf-8")
        return False

    try:
        title, image_map, articles = wsj_reader.read_epub(str(book))
    except Exception as exc:
        print(f"  SKIP: EPUB parse failed: {exc}")
        (book_output / "ERROR.txt").write_text(f"EPUB parse failed: {exc}\n", encoding="utf-8")
        return False

    ParserDebugger().dump(articles, book_output / "parser_debug.json")
    paragraph_report = ParagraphTracer().trace(articles, book_output / "paragraph_trace.json")
    ParagraphTracer().print_summary(paragraph_report)
    dom_trace = [article.get("_dom_node_trace", {}) for article in articles]
    unique_dom_nodes = sum(int(item.get("unique_dom_nodes", 0) or 0) for item in dom_trace)
    duplicate_dom_node_visits = sum(int(item.get("duplicate_dom_node_visits", 0) or 0) for item in dom_trace)
    print("DOM Node Trace")
    print(f"Unique DOM nodes: {unique_dom_nodes}")
    print(f"Duplicate DOM node visits: {duplicate_dom_node_visits}")
    links = ContinuationResolver().resolve(articles)
    ContinuationMerger().merge(articles, links)

    topic_filter = TopicFilter()
    candidates = topic_filter.filter_articles(articles)
    topic_filter.write_reports(candidates, book_output)
    topic_filter.print_stats()

    progress_file = _progress_path(book_output)
    progress = _load_progress(progress_file, book, len(articles))
    saved = progress.setdefault("translations", {})

    if service is None or not TRANSLATE:
        print("  API not configured; keeping original text and generating HTML")
    else:
        for article in candidates:
            source_index = int(article.get("source_index", 0))
            key = str(source_index)
            if key in saved:
                article.update(saved[key])
                continue
            print(f"  Translating {source_index + 1}/{len(articles)}: {article.get('title', '')[:40]}")
            translated = _translate_with_retry(service, article, book.name, source_index + 1)
            article.update({k: translated.get(k, article.get(k, "")) for k in ("title", "subtitle", "annotation", "byline", "paragraphs")})
            saved[key] = {k: article[k] for k in ("title", "subtitle", "annotation", "byline", "paragraphs")}
            _save_progress(progress_file, progress)
            time.sleep(DELAY_SECONDS)

    if service is not None and ANALYZE:
        for article in candidates:
            source_index = int(article.get("source_index", 0))
            key = str(source_index)
            if saved.get(key, {}).get("analysis"):
                article["analysis"] = saved[key]["analysis"]
                continue
            print(f"  Analyzing {source_index + 1}/{len(articles)}: {article.get('title', '')[:40]}")
            analysis = _analyze_article(service, article)
            if analysis is not None:
                article["analysis"] = analysis
                saved.setdefault(key, {})["analysis"] = analysis
                _save_progress(progress_file, progress)
            time.sleep(DELAY_SECONDS)

    for article in articles:
        article["_source"] = book.name
    wsj_reader.OUTPUT_DIR = book_output
    wsj_reader.IMAGES_DIR = book_output / "images"
    wsj_reader.save_output(title, image_map, articles)
    progress["status"] = "completed"
    progress["articles"] = len(articles)
    _save_progress(progress_file, progress)
    return True


def main() -> None:
    books = find_books()
    if not books:
        print(f"ERROR: books folder has no EPUB files: {BOOKS_DIR}")
        return
    config = AIServiceConfig.from_env()
    service = AIService(config) if config.is_active else None
    print(f"Found {len(books)} EPUB file(s); processing in filename order")
    completed = failed = 0
    for number, book in enumerate(books, 1):
        print(f"\n[{number}/{len(books)}] {book.name}")
        if process_book(book, service):
            completed += 1
        else:
            failed += 1
    print(f"\nQueue complete: {completed} succeeded, {failed} failed/skipped")


if __name__ == "__main__":
    main()
