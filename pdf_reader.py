"""PDF to HTML converter for text-based research PDFs."""

from __future__ import annotations

import html
import re
from collections import Counter
from pathlib import Path

from topic_filter import TopicFilter


def _require_pdfplumber():
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "PDF parsing requires pdfplumber. Install it with "
            "'python -m pip install pdfplumber' (or use the Python interpreter "
            "selected by run_pdf.bat)."
        ) from exc
    return pdfplumber


def _require_pymupdf():
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError(
            "PDF text extraction requires PyMuPDF. Install it with "
            "'python -m pip install PyMuPDF'."
        ) from exc
    return pymupdf


def _normalise_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().casefold()


def _page_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\r\n", "\n").splitlines() if line.strip()]


def _repeated_margin_lines(page_lines: list[list[str]]) -> set[str]:
    """Find lines repeated at the top or bottom of multiple pages."""
    if len(page_lines) < 2:
        return set()

    candidates: list[str] = []
    for lines in page_lines:
        # Restrict detection to margins, so repeated body headings are not removed.
        for line in lines[:3] + lines[-3:]:
            normalised = _normalise_line(line)
            if len(normalised) >= 3:
                candidates.append(normalised)

    counts = Counter(candidates)
    required = max(2, (len(page_lines) + 1) // 2)
    return {line for line, count in counts.items() if count >= required}


def _paragraphs_from_text(text: str, repeated_margins: set[str] | None = None) -> list[str]:
    paragraphs: list[str] = []
    lines = _page_lines(text)
    if repeated_margins:
        lines = [line for line in lines if _normalise_line(line) not in repeated_margins]
    for block in re.split(r"\n\s*\n", "\n".join(lines)):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if lines:
            paragraphs.append(" ".join(lines))
    return paragraphs


def _deduplicate_and_join_pages(pages: list[list[str]]) -> list[list[str]]:
    """Remove exact repeated paragraphs and join obvious cross-page continuations."""
    seen: set[str] = set()
    cleaned: list[list[str]] = []
    terminal = ".!?。！？:：;；)]}）】」』"

    # Keep the source ASCII-safe; these escapes cover common CJK terminators.
    terminal = ".!?;:)]}" + "\u3002\uff01\uff1f\uff1a\uff1b\uff09\u3011\u300d\u300f"
    for paragraphs in pages:
        current: list[str] = []
        for paragraph in paragraphs:
            key = _normalise_line(paragraph)
            if not key or key in seen:
                continue
            seen.add(key)
            if current and not current[-1].endswith(tuple(terminal)):
                current[-1] = f"{current[-1]} {paragraph}"
            else:
                current.append(paragraph)
        if cleaned and current and cleaned[-1] and not cleaned[-1][-1].endswith(tuple(terminal)):
            cleaned[-1][-1] = f"{cleaned[-1][-1]} {current.pop(0)}"
        cleaned.append(current)
    return cleaned


def read_pdf(pdf_path: str | Path) -> tuple[str, list[dict]]:
    """Extract a PDF into the article shape used by the reader pipeline."""
    pymupdf = _require_pymupdf()
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")

    title = path.stem.replace("_", " ").replace("-", " ").strip() or "PDF document"
    articles: list[dict] = []
    document = pymupdf.open(path)
    try:
        metadata_title = (document.metadata or {}).get("title")
        if metadata_title and str(metadata_title).strip():
            title = str(metadata_title).strip()
        page_paragraphs = [_paragraphs_from_blocks(page) for page in document]
        page_paragraphs = _deduplicate_and_join_pages(page_paragraphs)

        for number, paragraphs in enumerate(page_paragraphs, start=1):
            articles.append({
                "title": f"Page {number}",
                "subtitle": "",
                "annotation": "",
                "byline": "",
                "paragraphs": paragraphs,
                "images": [],
                "_source": path.name,
                "_page": number,
            })

    finally:
        document.close()

    if articles and not any(article["paragraphs"] for article in articles):
        raise ValueError(
            "PDF contains no extractable text. It may be scanned; OCR support is not enabled yet."
        )
    if not articles:
        raise ValueError("PDF contains no pages")
    return title, articles


def filter_candidate_articles(articles: list[dict], output_root: Path | str | None = None, threshold: int = 15) -> list[dict]:
    """Apply the shared local topic filter to PDF-derived articles."""
    topic_filter = TopicFilter(threshold=threshold)
    candidates = topic_filter.filter_articles(articles)
    if output_root is not None:
        topic_filter.write_reports(candidates, output_root)
    return candidates


def _paragraphs_from_blocks(page) -> list[str]:
    """Extract selectable paragraphs from PyMuPDF's positioned text blocks."""
    paragraphs: list[str] = []
    for block in page.get_text("blocks", sort=True):
        if len(block) < 7 or block[6] != 0:  # Ignore image/drawing blocks.
            continue
        raw = str(block[4]).replace("\r", "\n").strip()
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines() if line.strip()]
        if lines:
            paragraphs.append(" ".join(lines))
    return paragraphs


def _render_html(title: str, source_name: str, articles: list[dict]) -> str:
    toc = "\n".join(
        f'<li><a href="#page-{index}">Page {html.escape(str(article.get("_page", index)))}</a></li>'
        for index, article in enumerate(articles, start=1)
    )
    sections: list[str] = []
    for index, article in enumerate(articles, start=1):
        paragraphs = "\n".join(
            f"<p>{html.escape(paragraph)}</p>"
            for paragraph in article.get("paragraphs", [])
        ) or '<p class="empty">No extractable text on this page.</p>'
        sections.append(
            f'<section id="page-{index}"><h2>Page {html.escape(str(article.get("_page", index)))}</h2>\n'
            f"{paragraphs}\n"
            '<p class="back-link"><a href="#toc">Back to contents</a></p></section>'
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - PDF Reader</title>
<style>
body {{ margin:0; padding:1rem; background:#f5f5f5; color:#202124; font-family:Georgia,'Times New Roman',serif; line-height:1.65; }}
.container {{ max-width:820px; margin:auto; background:white; padding:2rem 2.5rem; }}
h1 {{ font-size:1.6rem; margin:0 0 .25rem; }} .source {{ color:#777; font: .85rem Arial,sans-serif; margin-bottom:2rem; }}
#toc {{ background:#f1f3f4; padding:1rem 1.5rem; margin-bottom:2rem; }} #toc h2 {{ font:600 1rem Arial,sans-serif; margin-top:0; }}
#toc a,.back-link a {{ color:#185abc; text-decoration:none; }} section {{ border-top:1px solid #ddd; padding-top:1.5rem; margin-top:2rem; }}
section h2 {{ font-size:1.25rem; }} p {{ text-align:justify; }} .empty {{ color:#888; font-style:italic; }} .back-link {{ font:.8rem Arial,sans-serif; text-align:left; }}
@media (max-width:600px) {{ body {{ padding:0; }} .container {{ padding:1rem; }} }}
</style></head><body><main class="container">
<h1>{html.escape(title)}</h1><p class="source">Source: {html.escape(source_name)} - PDF to HTML</p>
<nav id="toc"><h2>Table of contents</h2><ol>{toc}</ol></nav>
{''.join(sections)}</main></body></html>"""


def convert_pdf_to_html(pdf_path: str | Path, output_path: str | Path | None = None) -> Path:
    path = Path(pdf_path)
    title, articles = read_pdf(path)
    target = Path(output_path) if output_path else path.with_suffix(".html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_render_html(title, path.name, articles), encoding="utf-8")
    return target


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Convert a text-based PDF to HTML")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    print(f"HTML: {convert_pdf_to_html(args.pdf, args.output)}")


if __name__ == "__main__":
    main()
