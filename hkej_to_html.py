#!/usr/bin/env python3
"""Convert HKEJ scraper TXT/JSON output into a Daily Reader style HTML file."""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _read_text(path: Path) -> str:
    """Read UTF-8 (including BOM) and gracefully fall back for old Windows TXT files."""
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="cp936", errors="replace")


def _parse_txt(path: Path) -> tuple[dict, list[dict]]:
    text = _read_text(path).replace("\r\n", "\n")
    header, _, body = text.partition("\n\n")
    metadata: dict[str, str] = {"source": "https://www.hkej.com/instantnews"}
    for line in header.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()

    blocks = re.split(r"(?m)^={10,}\s*$", body)
    articles: list[dict] = []
    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        fields: dict[str, str] = {}
        content_lines: list[str] = []
        in_content = False
        for line in lines:
            if line.startswith("正文:"):
                in_content = True
                remainder = line.partition(":")[2].strip()
                if remainder:
                    content_lines.append(remainder)
            elif not in_content and re.match(r"^(标题|链接|分类|状态):", line):
                key, value = line.split(":", 1)
                fields[key] = value.strip()
            elif in_content:
                content_lines.append(line)
        if fields.get("标题"):
            articles.append({
                "title": fields.get("标题", "未命名新闻"),
                "url": fields.get("链接", ""),
                "category": fields.get("分类", ""),
                "content": "\n".join(content_lines).strip() or fields.get("状态", ""),
            })
    return metadata, articles


def _parse_json(path: Path) -> tuple[dict, list[dict]]:
    data = json.loads(_read_text(path))
    metadata = {
        "抓取时间": str(data.get("time", "")),
        "抓取页数": str(data.get("pages", "")),
        "来源": "https://www.hkej.com/instantnews",
    }
    articles = []
    for item in data.get("articles", []):
        articles.append({
            "title": str(item.get("title") or "未命名新闻"),
            "url": str(item.get("url") or ""),
            "category": str(item.get("category") or ""),
            "content": str(item.get("content") or "未能提取正文"),
        })
    return metadata, articles


def _parse_txt_utf8(path: Path) -> tuple[dict, list[dict]]:
    """Parse the UTF-8 Chinese labels written by the PowerShell scraper."""
    text = _read_text(path).replace("\r\n", "\n")
    header, _, body = text.partition("\n\n")
    metadata: dict[str, str] = {"source": "https://www.hkej.com/instantnews"}
    for line in header.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()

    labels = {
        "title": "\u6807\u9898",
        "url": "\u94fe\u63a5",
        "category": "\u5206\u7c7b",
        "content": "\u6b63\u6587",
        "status": "\u72b6\u6001",
    }
    articles: list[dict] = []
    for block in re.split(r"(?m)^={10,}\s*$", body):
        fields: dict[str, str] = {}
        content_lines: list[str] = []
        in_content = False
        for line in block.strip().splitlines():
            if line.startswith(labels["content"] + ":"):
                in_content = True
                remainder = line.split(":", 1)[1].strip()
                if remainder:
                    content_lines.append(remainder)
            elif not in_content and any(line.startswith(labels[key] + ":") for key in ("title", "url", "category", "status")):
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
            elif in_content:
                content_lines.append(line)
        if fields.get(labels["title"]):
            articles.append({
                "title": fields[labels["title"]],
                "url": fields.get(labels["url"], ""),
                "category": fields.get(labels["category"], ""),
                "content": "\n".join(content_lines).strip() or fields.get(labels["status"], ""),
            })
    return metadata, articles


def parse_input(path: Path) -> tuple[dict, list[dict]]:
    if path.suffix.lower() == ".json":
        return _parse_json(path)
    return _parse_txt_utf8(path)


def _paragraphs(content: str) -> list[str]:
    content = content.strip()
    if not content:
        return ["未能提取正文"]
    # PowerShell's scraper writes one long line; preserve deliberate paragraphs
    # and make quoted leading markers look natural in the reader.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    return paragraphs or [content]


def build_html(metadata: dict, articles: list[dict], input_path: Path) -> str:
    title = "信报即时新闻"
    fetched = metadata.get("抓取时间") or metadata.get("抓取时间") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    toc = "\n".join(
        f'<li><a href="#article-{i}">{i}. {html.escape(article["title"])}</a></li>'
        for i, article in enumerate(articles, 1)
    )
    sections = []
    for i, article in enumerate(articles, 1):
        paragraphs = "\n".join(
            f"<p>{html.escape(p.lstrip('> '))}</p>" for p in _paragraphs(article["content"])
        )
        source = article.get("url") or metadata.get("来源") or metadata.get("source", "")
        category = article.get("category", "")
        details = " · ".join(x for x in (category, source) if x)
        sections.append(
            f'<section id="article-{i}">\n'
            f'  <h2>{html.escape(article["title"])}</h2>\n'
            f'  <p class="source">{html.escape(details)}</p>\n'
            f'  <div class="article-body">{paragraphs}</div>\n'
            f'  <p class="back-link"><a href="#toc">返回目录</a></p>\n'
            f'</section>'
        )
    body = "\n".join(sections) or '<p class="empty">没有找到可转换的新闻。</p>'
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — Daily Reader</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 1rem; background: #fafafa; color: #1a1a1a; font-family: Georgia, 'Times New Roman', serif; line-height: 1.7; }}
.container {{ max-width: 720px; margin: 0 auto; padding: 2rem 2.5rem; background: #fff; border: 1px solid #ddd; border-radius: 4px; }}
h1.page-title {{ margin: 0 0 .25rem; font-size: 1.4rem; }}
.date-line {{ margin: 0 0 2rem; color: #666; font-size: .85rem; font-style: italic; }}
#toc {{ margin-bottom: 2.5rem; padding: 1rem 1.5rem; background: #f5f5f5; border-left: 3px solid #333; }}
#toc h2 {{ margin: 0 0 .75rem; font: 1rem Arial, sans-serif; text-transform: uppercase; letter-spacing: .05em; }}
#toc ol {{ margin: 0; padding-left: 1.5rem; }}
#toc li {{ margin-bottom: .3rem; font: .9rem Arial, sans-serif; }}
a {{ color: #1a5276; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
section {{ margin-bottom: 2rem; }} section h2 {{ margin-bottom: .25rem; font-size: 1.3rem; }}
.source {{ margin: 0 0 .75rem; color: #999; font: .75rem Arial, sans-serif; overflow-wrap: anywhere; }}
.article-body p {{ margin: 0 0 1rem; }} .back-link {{ margin-top: 1rem; font: .8rem Arial, sans-serif; }}
.empty {{ color: #777; }}
@media (max-width: 600px) {{ body {{ padding: 0; }} .container {{ padding: 1.25rem; border: 0; }} }}
</style>
</head>
<body>
<main class="container">
  <h1 class="page-title">{html.escape(title)}</h1>
  <p class="date-line">抓取时间：{html.escape(fetched)} · 来源文件：{html.escape(input_path.name)}</p>
  <nav id="toc"><h2>目录</h2><ol>{toc}</ol></nav>
{body}
</main>
</body>
</html>'''


def find_latest() -> Path:
    candidates = list((ROOT / "outputs").glob("hkej_news_*.txt")) + list((ROOT / "work" / "outputs").glob("hkej_news_*.json"))
    if not candidates:
        raise FileNotFoundError("未找到 HKEJ TXT/JSON 输出文件")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main() -> None:
    parser = argparse.ArgumentParser(description="将 HKEJ TXT/JSON 转换为 Daily Reader HTML")
    parser.add_argument("input", nargs="?", type=Path, help="输入的 .txt 或 .json 文件")
    parser.add_argument(
        "-o", "--output", type=Path,
        help="输出文件路径；省略时自动命名为 output/hkejYYYYMMDDHHMMSS.html",
    )
    parser.add_argument("--latest", action="store_true", help="自动选择最近生成的 HKEJ 输出")
    args = parser.parse_args()
    input_path = find_latest() if args.latest or args.input is None else args.input
    metadata, articles = parse_input(input_path)
    output_path = args.output or (ROOT / "output" / f"hkej{datetime.now().strftime('%Y%m%d%H%M%S')}.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_html(metadata, articles, input_path), encoding="utf-8")
    print(f"HTML: {output_path} ({len(articles)} articles)")


if __name__ == "__main__":
    main()
