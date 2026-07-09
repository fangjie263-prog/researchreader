#!/usr/bin/env python3
"""信报即时新闻爬虫 — 输出 UTF-8 JSON，日志纯 ASCII。"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import unquote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = "https://www.hkej.com"
LINK_RE = re.compile(r'(?<=href=")(/instantnews/[a-z]+/article/\d+/[^"]*)(?=")')
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 30


def safe_print(*args, **kwargs):
    """Console prints that never crash on Windows CP1252."""
    try:
        print(*args)
    except (UnicodeEncodeError, OSError):
        pass


class _Stripper(HTMLParser):
    """从 HTML 中提取纯文本。"""

    def __init__(self):
        super().__init__()
        self._skip = False
        self._out = []

    def handle_starttag(self, tag, _):
        self._skip = tag in ("script", "style")

    def handle_endtag(self, tag):
        self._skip = tag in ("script", "style")

    def handle_data(self, data):
        if not self._skip:
            self._out.append(data)

    def text(self):
        return re.sub(r"\s+", " ", "".join(self._out)).strip()


def _fetch(url: str) -> str:
    """GET 网页，返回 HTML 字符串。"""
    req = Request(url, headers={"User-Agent": UA})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError) as e:
        raise RuntimeError(str(e)) from e


def _extract_title(html: str) -> str:
    """? HTML ???????????: h1 > og:title > title tag."""
    # 1. <h1>
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if m:
        text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if text:
            return text
    # 2. og:title
    m = re.search(r'property="og:title".*?content="(.*?)"', html, re.DOTALL)
    if m:
        text = m.group(1).strip()
        if text:
            return text
    # 3. <title> tag, remove site suffix
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    if m:
        text = m.group(1).strip()
        for sep in (" - ", "\u2032", "|"):
            if sep in text:
                text = text.split(sep)[0].strip()
        return text if text else "?"
    return "?"


def scrape(num_pages: int = 5) -> str:
    seen: dict[str, None] = {}

    safe_print(f"=== Fetching hkej.com (pages={num_pages}) ===")

    # 1. Collect article links
    for page in range(1, num_pages + 1):
        url = f"{BASE}/instantnews" if page == 1 else f"{BASE}/instantnews/index?page={page}"
        safe_print(f"[{page}/{num_pages}] Fetching list page ...", end="", flush=True)
        try:
            html = _fetch(url)
            for m in LINK_RE.findall(html):
                seen[m] = None
            safe_print(f" OK ({len(seen)} articles)")
        except RuntimeError as e:
            safe_print(f" FAIL ({e})")
        time.sleep(0.5)

    links = list(seen.keys())
    total = len(links)
    if total == 0:
        safe_print("No article links found, exiting.")
        return ""

    # 2. Fetch each article body
    articles: list[dict] = []
    ok = fail = 0
    for i, rel in enumerate(links, 1):
        full = BASE + rel
        parts = rel.strip("/").split("/")
        cat = parts[2] if len(parts) > 2 else "?"
        title = "?"

        safe_print(f"\r[{i}/{total}] Parsing article ...", end="", flush=True)

        try:
            article_html = _fetch(full)
            title = _extract_title(article_html)
            marker = article_html.find("article-content")
            if marker > 0:
                rest = article_html[marker:]
                end = rest.find("</div>")
                if end > 0:
                    inner = rest[: end + 6]
                    s = _Stripper()
                    s.feed(inner)
                    body = s.text()

                    # Strip leftover HTML fragment like "article-content'> "
                    body = re.sub(r"^article-content['\"]?\s*", "", body)
                else:
                    body = ""
            else:
                body = ""
        except RuntimeError:
            body = ""
            fail += 1

        articles.append({
            "title": title,
            "content": body,
        })
        if body:
            ok += 1
        else:
            fail += 1

        time.sleep(0.4)

    safe_print(f"\r[{total}/{total}] Done.")

    # 3. Save UTF-8 JSON
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"hkej_news_{now}.json")

    output = {
        "report": "HKEJ Instant News Scraper",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pages": num_pages,
        "total": total,
        "success": ok,
        "failed": fail,
        "articles": articles,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    safe_print(f"Saved: {path}")
    return path


def main():
    p = argparse.ArgumentParser(description="信报即时新闻爬虫")
    p.add_argument("-n", "--pages", type=int, default=5, help="抓取页数")
    args = p.parse_args()
    scrape(args.pages)


if __name__ == "__main__":
    main()

