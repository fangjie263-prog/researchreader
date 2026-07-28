"""Topic-first reading recommendations for existing output Markdown/HTML files."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

from ai_config import AIServiceConfig
from ai_service import AIService, AIServiceError
from topic_manager import load_topics, topic_context
from topic_filter import TopicFilter


ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "output"


def _plain_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _read_articles(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".html":
        text = _plain_html(text)
        return [{"title": path.stem, "text": text}]

    articles: list[dict] = []
    title = path.stem
    body: list[str] = []
    for line in text.splitlines():
        heading = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if heading:
            if body:
                articles.append({"title": title, "text": " ".join(body)})
                body = []
            title = heading.group(1).strip()
        elif line.strip() and not re.fullmatch(r"[-*_]{3,}", line.strip()):
            body.append(line.strip())
    if body:
        articles.append({"title": title, "text": " ".join(body)})
    return articles


def _topic_terms() -> list[str]:
    terms: list[str] = []
    for topic in load_topics():
        terms.append(topic.get("name_zh", ""))
        terms.extend(topic.get("keywords_zh", []))
        terms.extend(topic.get("keywords_en", []))
        terms.extend(topic.get("related_topics", []))
    return [term.casefold() for term in terms if term.strip()]


def _matches_topics(article: dict, terms: list[str]) -> list[str]:
    haystack = f"{article['title']} {article['text']}".casefold()
    return [term for term in terms if term in haystack]


def collect_candidates(root: Path = OUTPUT_ROOT) -> list[dict]:
    candidates: list[dict] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".html"}:
            continue
        if path.name in {"reading_recommendations.md", "reading_recommendations.html"}:
            continue
        if path.name in {"candidate_articles.md", "candidate_articles.json"}:
            continue
        for article in _read_articles(path):
            article.update({"source": str(path.relative_to(root))})
            candidates.append(article)
    return candidates


def build_report(results: list[dict]) -> tuple[str, str]:
    md = ["# Reading Recommendations", "", "Generated after local topic filtering and AI screening.", ""]
    sections: list[str] = []
    for index, item in enumerate(results, start=1):
        md.extend([
            f"## {index}. {item['title']}", "",
            f"- Source: `{item['source']}`",
            f"- Priority: {item.get('priority', 0)}/5",
            f"- Matched topics: {', '.join(item.get('matched_topics', item.get('local_matches', [])))}", "",
            f"**阅读理由（中文）**：{item.get('reason_zh', '')}", "",
            f"**Reading reason (English)**: {item.get('reason_en', '')}", "",
            f"**摘要（中文）**：{item.get('summary_zh', '')}", "",
            f"**Summary (English)**: {item.get('summary_en', '')}", "", "---", "",
        ])
        sections.append(
            f'<section><h2>{index}. {html.escape(item["title"])}</h2>'
            f'<p class="meta">{html.escape(item["source"])} · Priority {item.get("priority", 0)}/5</p>'
            f'<h3>阅读理由（中文）</h3><p>{html.escape(item.get("reason_zh", ""))}</p>'
            f'<h3>Reading reason (English)</h3><p>{html.escape(item.get("reason_en", ""))}</p>'
            f'<h3>摘要（中文）</h3><p>{html.escape(item.get("summary_zh", ""))}</p>'
            f'<h3>Summary (English)</h3><p>{html.escape(item.get("summary_en", ""))}</p></section>'
        )
    html_text = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Reading Recommendations</title>
<style>body{font-family:Arial,sans-serif;line-height:1.7;max-width:900px;margin:auto;padding:2rem;color:#222}section{border-top:1px solid #ddd;padding:1rem 0}.meta{color:#777;font-size:.9rem}h3{margin-bottom:.2rem}</style>
</head><body><h1>Reading Recommendations</h1><p>先按关注主题本地筛选，再由 AI 判断是否推荐阅读。</p>""" + "".join(sections) + "</body></html>"
    return "\n".join(md), html_text


def build_json_records(results: list[dict]) -> list[dict]:
    records: list[dict] = []
    for index, item in enumerate(results, start=1):
        records.append({
            "article_id": f"article_{index:03d}",
            "title": item.get("title", ""),
            "priority": item.get("priority", 0),
            "matched_topics": item.get("matched_topics", item.get("local_matches", [])),
            "summary_zh": item.get("summary_zh", ""),
            "summary_en": item.get("summary_en", ""),
            "reason_zh": item.get("reason_zh", ""),
            "reason_en": item.get("reason_en", ""),
            "source_document": item.get("source", ""),
        })
    return records


def write_json_report(path: Path, results: list[dict]) -> Path:
    path.write_text(
        json.dumps(build_json_records(results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def run(root: Path = OUTPUT_ROOT) -> tuple[Path, Path, int]:
    config = AIServiceConfig.from_env()
    if not config.is_active:
        raise RuntimeError("AI is not configured. Run 'python ai_setup.py setup'.")
    articles = collect_candidates(root)
    topic_filter = TopicFilter()
    candidates = topic_filter.filter_articles(articles)
    topic_filter.write_reports(candidates, root)
    topic_filter.print_stats()
    service = AIService(config)
    results: list[dict] = []
    for candidate in candidates[:30]:
        try:
            screened = service.screen_article(candidate["title"], candidate["text"], topic_context())
        except AIServiceError as exc:
            print(f"Skipped {candidate['title'][:50]}: {exc}")
            continue
        if screened.get("recommend") is True:
            results.append({**candidate, **screened})
    results.sort(key=lambda item: int(item.get("priority", 0)), reverse=True)
    markdown, html_text = build_report(results)
    md_path = root / "reading_recommendations.md"
    html_path = root / "reading_recommendations.html"
    json_path = root / "reading_recommendations.json"
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")
    write_json_report(json_path, results)
    return md_path, html_path, len(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Screen existing output files and create reading recommendations")
    parser.add_argument("--root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    if not load_topics():
        raise SystemExit("No topics configured. Run: python topic_manager.py add \"人工智能\"")
    md_path, html_path, count = run(args.root)
    print(f"Recommended: {count}")
    print(f"Markdown: {md_path}")
    print(f"HTML: {html_path}")
    print(f"JSON: {args.root / 'reading_recommendations.json'}")


if __name__ == "__main__":
    main()
