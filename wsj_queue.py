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


ROOT = Path(__file__).resolve().parent
BOOKS_DIR = ROOT / "books"
OUTPUT_ROOT = ROOT / "output"
DELAY_SECONDS = float(os.environ.get("WSJ_API_DELAY", "3"))
RETRIES = int(os.environ.get("WSJ_API_RETRIES", "3"))


def _safe_name(path: Path) -> str:
    name = re.sub(r"[^0-9A-Za-z一-龥._-]+", "_", path.stem).strip("._")
    return name or "book"


def find_books() -> list[Path]:
    return sorted(BOOKS_DIR.glob("*.epub"), key=lambda p: p.name.casefold())


def validate_epub(path: Path) -> str | None:
    """Return a readable error instead of letting a corrupt EPUB abort the queue."""
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                return f"CRC 校验失败: {bad}"
    except (OSError, zipfile.BadZipFile) as exc:
        return f"EPUB/ZIP 无法读取: {exc}"
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
                raise AIServiceError("paragraphs 不是数组")
            return translated
        except (AIServiceError, OSError, ValueError) as exc:
            last_error = exc
            if attempt < RETRIES:
                wait = max(DELAY_SECONDS, 2 ** (attempt - 1) * 5)
                print(f"    {book_name} 第 {index} 篇失败，{wait:.0f} 秒后重试 ({attempt}/{RETRIES})")
                time.sleep(wait)
    raise AIServiceError(f"第 {index} 篇翻译失败: {last_error}")


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
        print(f"  SKIP: EPUB 解析失败: {exc}")
        (book_output / "ERROR.txt").write_text(f"EPUB 解析失败: {exc}\n", encoding="utf-8")
        return False

    progress_file = _progress_path(book_output)
    progress = _load_progress(progress_file, book, len(articles))
    saved = progress.setdefault("translations", {})
    if service is None:
        print("  API 未配置，保留原文并生成 HTML")
    else:
        for index, article in enumerate(articles):
            key = str(index)
            if key in saved:
                article.update(saved[key])
                continue
            print(f"  翻译 {index + 1}/{len(articles)}: {article.get('title', '')[:40]}")
            translated = _translate_with_retry(service, article, book.name, index + 1)
            article.update({k: translated.get(k, article.get(k, "")) for k in ("title", "subtitle", "annotation", "byline", "paragraphs")})
            saved[key] = {k: article[k] for k in ("title", "subtitle", "annotation", "byline", "paragraphs")}
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
        print(f"ERROR: books 文件夹没有 EPUB: {BOOKS_DIR}")
        return
    config = AIServiceConfig.from_env()
    service = AIService(config) if config.is_active and os.environ.get("WSJ_TRANSLATE", "1") != "0" else None
    print(f"发现 {len(books)} 本 EPUB，将按文件名顺序逐本处理")
    completed = failed = 0
    for number, book in enumerate(books, 1):
        print(f"\n[{number}/{len(books)}] {book.name}")
        if process_book(book, service):
            completed += 1
        else:
            failed += 1
    print(f"\n队列完成：成功 {completed} 本，失败/跳过 {failed} 本")


if __name__ == "__main__":
    main()
