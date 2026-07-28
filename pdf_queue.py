"""Sequential PDF extraction queue with WSJ-style per-file output folders."""

from __future__ import annotations

import html
import re
from pathlib import Path

from pdf_reader import _render_html, filter_candidate_articles, read_pdf


ROOT = Path(__file__).resolve().parent
BOOKS_DIR = ROOT / "books"
OUTPUT_ROOT = ROOT / "output"


def _safe_name(path: Path) -> str:
    name = re.sub(r"[^0-9A-Za-z一-龥._-]+", "_", path.stem).strip("._")
    return name or "pdf"


def find_pdfs() -> list[Path]:
    # Windows treats *.pdf and *.PDF as the same pattern; deduplicate by resolved path.
    found = {path.resolve(): path for path in BOOKS_DIR.iterdir() if path.is_file() and path.suffix.casefold() == ".pdf"}
    return sorted(found.values(), key=lambda path: path.name.casefold())


def _to_markdown(title: str, source: str, articles: list[dict]) -> str:
    parts = [f"# {title}", "", f"*Source: {source}*", "", "---", ""]
    for article in articles:
        parts.extend([f"## {article['title']}", ""])
        for paragraph in article.get("paragraphs", []):
            parts.extend([paragraph, ""])
        parts.extend(["---", ""])
    return "\n".join(parts)


def _save_output(pdf: Path, output_dir: Path, title: str, articles: list[dict]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "extracted_articles.md"
    markdown_path.write_text(_to_markdown(title, pdf.name, articles), encoding="utf-8")

    html_path = output_dir / "daily.html"
    html_path.write_text(_render_html(title, pdf.name, articles), encoding="utf-8")
    print(f"  MD:   {markdown_path}")
    print(f"  HTML: {html_path}")


def _render_visual_html(pdf: Path, output_dir: Path, title: str) -> Path:
    """Render each PDF page as an image so the magazine layout is preserved."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required for PDF rendering") from exc

    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    page_items: list[str] = []
    with pdfplumber.open(pdf) as document:
        for number, page in enumerate(document.pages, start=1):
            image_name = f"page-{number:03d}.png"
            image_path = pages_dir / image_name
            page.to_image(resolution=144).save(image_path, format="PNG")
            page_items.append(
                f'<figure id="page-{number}"><img src="pages/{image_name}" '
                f'alt="Page {number}" loading="lazy"><figcaption>Page {number}</figcaption></figure>'
            )

    contents = "\n".join(
        f'<li><a href="#page-{number}">Page {number}</a></li>'
        for number in range(1, len(page_items) + 1)
    )
    html_text = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} - PDF viewer</title>
<style>
body {{ margin:0; background:#333; color:#eee; font-family:Arial,sans-serif; }}
.toolbar {{ position:sticky; top:0; z-index:2; padding:12px 16px; background:#202020; }}
.toolbar h1 {{ display:inline; margin:0 20px 0 0; font-size:16px; }}
.toolbar a {{ color:#9ecbff; margin-right:10px; }}
main {{ padding:20px 10px 40px; }}
figure {{ width:min(100%, 1100px); margin:0 auto 24px; text-align:center; }}
img {{ display:block; width:100%; height:auto; background:white; box-shadow:0 2px 12px #111; }}
figcaption {{ padding:7px; color:#bbb; font-size:12px; }}
</style></head><body>
<div class="toolbar"><h1>{html.escape(title)}</h1><a href="#toc">目录</a></div>
<nav id="toc" class="toolbar"><strong>页面</strong><ol>{contents}</ol></nav>
<main>{''.join(page_items)}</main></body></html>"""
    html_path = output_dir / "daily.html"
    html_path.write_text(html_text, encoding="utf-8")
    return html_path


def process_pdf(pdf: Path) -> bool:
    output_dir = OUTPUT_ROOT / _safe_name(pdf)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        title, articles = read_pdf(pdf)
        candidates = filter_candidate_articles(articles, output_dir)
        print(f"  Local filter selected {len(candidates)} page article(s)")
        _save_output(pdf, output_dir, title, articles)
        print(f"  Pages: {len(articles)}")
        return True
    except Exception as exc:
        message = f"PDF parsing failed: {exc}"
        print(f"  SKIP: {message}")
        (output_dir / "ERROR.txt").write_text(message + "\n", encoding="utf-8")
        return False


def main() -> None:
    pdfs = find_pdfs()
    if not pdfs:
        print(f"ERROR: No PDF files found in {BOOKS_DIR}")
        return

    print(f"Found {len(pdfs)} PDF file(s); processing in filename order")
    completed = failed = 0
    for number, pdf in enumerate(pdfs, start=1):
        print(f"\n[{number}/{len(pdfs)}] {pdf.name}")
        if process_pdf(pdf):
            completed += 1
        else:
            failed += 1
    print(f"\nQueue complete: {completed} succeeded, {failed} failed/skipped")


if __name__ == "__main__":
    main()
