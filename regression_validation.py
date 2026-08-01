"""Post-render regression checks for the fixed PressReader EPUB sample."""
from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from wsj_reader import read_epub, save_output


SAMPLE_NAME = "the-wall-street-journal 01-08-2026 (Kobo).epub"


def _normal(text: object) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().casefold()


def validate_articles(articles: list[dict]) -> dict:
    titles = [_normal(a.get("title", "")) for a in articles if _normal(a.get("title", ""))]
    annotations = [_normal(a.get("annotation", "")) for a in articles if _normal(a.get("annotation", ""))]
    duplicate_titles = sorted({value for value in titles if titles.count(value) > 1})
    duplicate_annotations = sorted({value for value in annotations if annotations.count(value) > 1})
    body_duplicates = []
    for index, article in enumerate(articles):
        left = _normal(" ".join(map(str, article.get("paragraphs", []))))[:500]
        if not left:
            continue
        for other_index, other in enumerate(articles[index + 1:], index + 1):
            right = _normal(" ".join(map(str, other.get("paragraphs", []))))[:500]
            if right and SequenceMatcher(None, left, right).ratio() > 0.90:
                body_duplicates.append({"first": index, "second": other_index, "similarity": round(SequenceMatcher(None, left, right).ratio(), 4)})
    caption_headings = []
    for index, article in enumerate(articles):
        for paragraph in article.get("paragraphs", []):
            if isinstance(paragraph, dict) and paragraph.get("type") == "section_heading" and str(paragraph.get("text", "")).startswith("[Image"):
                caption_headings.append({"article": index, "text": paragraph.get("text", "")})
    return {
        "sample": SAMPLE_NAME, "articles": len(articles),
        "duplicate_titles": duplicate_titles, "duplicate_annotations": duplicate_annotations,
        "body_duplicates_over_90_percent": body_duplicates,
        "caption_headings": caption_headings,
        "passed": not (duplicate_titles or duplicate_annotations or body_duplicates or caption_headings),
    }


def run(sample: str | Path, output_root: str | Path = "output/regression") -> Path:
    sample_path = Path(sample)
    title, image_map, articles = read_epub(str(sample_path))
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    from wsj_reader import OUTPUT_DIR, IMAGES_DIR
    import wsj_reader
    old_output, old_images = OUTPUT_DIR, IMAGES_DIR
    try:
        wsj_reader.OUTPUT_DIR, wsj_reader.IMAGES_DIR = root, root / "images"
        save_output(title, image_map, articles)
    finally:
        wsj_reader.OUTPUT_DIR, wsj_reader.IMAGES_DIR = old_output, old_images
    report = validate_articles(articles)
    path = root / "validation.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", nargs="?", default=Path("books") / SAMPLE_NAME)
    parser.add_argument("--output", default=Path("output") / "validation.json")
    args = parser.parse_args()
    path = run(args.sample, Path(args.output).parent)
    report = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
