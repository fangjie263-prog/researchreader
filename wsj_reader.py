import html
import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from ebooklib import epub, ITEM_IMAGE, ITEM_DOCUMENT

from ai_model import AIConfig
from ai_processor import analyze_articles
from article_merger import ArticleMerger
from cleaner import ArticleCleaner
from continuation import ContinuationResolver
from topic_filter import TopicFilter
from research_picks import ResearchPicks
# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BOOKS_DIR = Path(__file__).parent / "books"
OUTPUT_DIR = Path(__file__).parent / "output"
IMAGES_DIR = OUTPUT_DIR / "images"

# EPUB item IDs that are not article content
SKIP_IDS = {"cover", "toc", "thumbnails", "ncx"}


# ---------------------------------------------------------------------------
# Find EPUB file
# ---------------------------------------------------------------------------

def find_epub() -> Path | None:
    if not BOOKS_DIR.exists():
        return None
    epubs = sorted(BOOKS_DIR.glob("*.epub"))
    return epubs[0] if epubs else None


# ---------------------------------------------------------------------------
# Read EPUB and extract articles
# ---------------------------------------------------------------------------

def read_epub(epub_path: str) -> tuple[str, dict[str, bytes], list[dict]]:
    book = epub.read_epub(epub_path)

    # Book title from metadata
    meta = book.get_metadata("DC", "title")
    book_title = meta[0][0] if meta else "Unknown"

    # Collect all images into a dict keyed by safe filename
    image_map: dict[str, bytes] = {}

    # Build a lookup: relative_path -> bytes  for fast image resolution
    image_lookup: dict[str, bytes] = {}
    for img_item in book.get_items_of_type(ITEM_IMAGE):
        path = img_item.get_name().lstrip("./")
        image_lookup[path] = img_item.get_content()

    articles: list[dict] = []

    # Go through spine order
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        item_id = getattr(item, "id", "")
        if item_id in SKIP_IDS:
            continue

        html = item.get_content().decode("utf-8")
        # EPUB content documents are XHTML/XML, not loose HTML.
        soup = BeautifulSoup(html, "lxml-xml")

        # Skip files without article containers
        art_divs = soup.find_all("div", class_="art-cnt")
        if not art_divs:
            continue

        # Base directory for resolving relative paths within this XHTML file
        xhtml_path = item.get_name()
        base_dir = str(Path(xhtml_path).parent)

        for art_div in art_divs:
            article = _parse_article(art_div, base_dir, image_lookup, image_map)
            articles.append(article)

    articles = ArticleCleaner().clean_articles(articles)
    return book_title, image_map, ArticleMerger().merge(articles)


def _same_article_field(left: str, right: str) -> bool:
    """Return whether two non-empty article metadata fields identify a match."""
    if not left or not right:
        return False
    if left == "Untitled" or right == "Untitled":
        return False
    return left.strip() == right.strip()


def should_merge_articles(previous: dict, current: dict) -> bool:
    """Return whether two consecutive parsed fragments belong to one article."""
    return any(
        _same_article_field(previous.get(field, ""), current.get(field, ""))
        for field in ("title", "byline", "subtitle")
    )


def deduplicate_paragraphs(paragraphs: list[str]) -> list[str]:
    """Remove repeated paragraphs while preserving their first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
        key = paragraph.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(paragraph)
    return result


def _deduplicate_images(images: list[dict]) -> list[dict]:
    """Keep the first occurrence of each image in article order."""
    result: list[dict] = []
    seen: set[str] = set()
    for image in images:
        key = image.get("src", "")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(image)
    return result


def merge_articles(articles: list[dict]) -> list[dict]:
    """Merge consecutive EPUB fragments that represent the same article."""
    if not articles:
        return []

    merged: list[dict] = []
    for article in articles:
        if not merged or not should_merge_articles(merged[-1], article):
            merged.append(article)
            continue

        target = merged[-1]
        target["paragraphs"] = deduplicate_paragraphs(
            target.get("paragraphs", []) + article.get("paragraphs", [])
        )
        target["images"] = _deduplicate_images(
            target.get("images", []) + article.get("images", [])
        )

        # Keep any metadata that was only present in the later fragment.
        for field in ("title", "subtitle", "annotation", "byline"):
            if not target.get(field) and article.get(field):
                target[field] = article[field]

    return merged


def _resolve_image(src: str, base_dir: str) -> str | None:
    """Resolve a relative image src to a normalized path inside the EPUB."""
    # Handle both forward and back slashes, strip leading ./ or ../
    clean = src.replace("\\", "/").lstrip("./")
    # If already absolute-ish, try as-is
    if "/" in clean or "\\" in clean:
        return clean
    # Otherwise prepend base directory
    return f"{base_dir}/{clean}"


def _save_image(rel_path: str, image_lookup: dict[str, bytes], image_map: dict[str, bytes]) -> str | None:
    """Look up image in EPUB, save to output/images/, return safe filename."""
    if rel_path not in image_lookup:
        return None

    # Safe filename: replace special chars
    safe = re.sub(r"[^a-zA-Z0-9_.\-]", "_", rel_path)

    if safe not in image_map:
        image_map[safe] = image_lookup[rel_path]

    return safe


def _dom_node_summary(node: Tag) -> dict:
    """Return a lightweight description of the DOM node that produced text."""
    classes = node.get("class", [])
    if not isinstance(classes, list):
        classes = [str(classes)]
    return {
        "tag": node.name,
        "classes": classes,
    }


def _register_dom_visit(seen_nodes: set[int], node: Tag) -> tuple[bool, int]:
    node_id = id(node)
    duplicate = node_id in seen_nodes
    if not duplicate:
        seen_nodes.add(node_id)
    return duplicate, node_id


def _parse_article(art_div: Tag, base_dir: str, image_lookup: dict, image_map: dict) -> dict:
    """Parse a single <div class=\"art-cnt\"> into structured data."""
    result = {
        "title": "",
        "subtitle": "",
        "annotation": "",
        "byline": "",
        "paragraphs": [],
        "images": [],
        "_paragraph_sources": [],
        "_dom_node_trace": {
            "unique_dom_nodes": 0,
            "duplicate_dom_node_visits": 0,
        },
    }

    # --- Title area ---
    title_area = art_div.find("div", class_="art-title-area")
    if title_area:
        el = title_area.find("div", class_="title")
        if el:
            result["title"] = el.get_text(strip=True)

        el = title_area.find("div", class_="subtitle")
        if el:
            result["subtitle"] = el.get_text(strip=True)

        el = title_area.find("div", class_="annotation")
        if el:
            result["annotation"] = el.get_text(strip=True)

        el = title_area.find("span", class_="byline")
        if not el:
            el = title_area.find("span", class_="copyright")
        if el:
            raw = el.get_text(strip=True)
            result["byline"] = re.sub(r"^by\s+", "", raw, flags=re.IGNORECASE)

    # --- Body: recursively walk nested div/section wrappers ---
    seen_images: set[str] = set()
    seen_nodes: set[int] = set()
    duplicate_dom_node_visits = 0

    def record_dom_visit(node: Tag) -> bool:
        nonlocal duplicate_dom_node_visits
        duplicate, _ = _register_dom_visit(seen_nodes, node)
        if duplicate:
            duplicate_dom_node_visits += 1
            result["_dom_node_trace"]["duplicate_dom_node_visits"] = duplicate_dom_node_visits
            return True
        result["_dom_node_trace"]["unique_dom_nodes"] = len(seen_nodes)
        return False

    def visit(container: Tag) -> None:
        if record_dom_visit(container):
            return
        for child in container.children:
            if not isinstance(child, Tag):
                continue

            cls = child.get("class", [])

            # Skip structural/header areas wherever they occur in the tree.
            if any(c in cls for c in ("art-cnt", "art-header", "legal-header", "art-title-area")):
                continue

            if child.name == "p":
                text = child.get_text(strip=True)
                if text:
                    result["paragraphs"].append(text)
                    result["_paragraph_sources"].append({
                        "type": "paragraph",
                        "text": text,
                        "node": _dom_node_summary(child),
                    })
                continue

            if "img-art" in cls:
                img_tag = child.find("img")
                caption_tag = child.find("span", class_="img-text")
                if img_tag:
                    src = img_tag.get("src", "")
                    alt = img_tag.get("alt", "")
                    if src:
                        resolved = _resolve_image(src, base_dir)
                        if resolved and resolved not in seen_images:
                            seen_images.add(resolved)
                            safe = _save_image(resolved, image_lookup, image_map)
                            if safe:
                                result["images"].append({
                                    "src": safe,
                                    "alt": alt,
                                    "caption": caption_tag.get_text(" ", strip=True) if caption_tag else "",
                                })
                                if caption_tag:
                                    caption = f"[Image: {caption_tag.get_text(strip=True)}]"
                                    result["paragraphs"].append(caption)
                                    result["_paragraph_sources"].append({
                                        "type": "image_caption",
                                        "text": caption,
                                        "node": _dom_node_summary(caption_tag),
                                    })
                continue

            visit(child)

    visit(art_div)
    result["_dom_node_trace"]["unique_dom_nodes"] = len(seen_nodes)
    result["_dom_node_trace"]["duplicate_dom_node_visits"] = duplicate_dom_node_visits

    # Fallback: use title as identifier
    if not result["title"]:
        result["title"] = "Untitled"

    return result


# ---------------------------------------------------------------------------
# Convert article to Markdown
# ---------------------------------------------------------------------------

def to_markdown(article: dict) -> str:
    lines: list[str] = []

    if article["title"]:
        lines.append(f"# {article['title']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    if article["subtitle"]:
        lines.append(f"**{article['subtitle']}**")
        lines.append("")

    if article["annotation"]:
        lines.append(f"> {article['annotation']}")
        lines.append("")

    if article["byline"]:
        lines.append(f"*By {article['byline']}*")
        lines.append("")

    for para in article["paragraphs"]:
        lines.append(para["text"] if isinstance(para, dict) else para)
        lines.append("")

    for img in article["images"]:
        lines.append(f"![{img['alt']}]({img['src']})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Save output
# ---------------------------------------------------------------------------

def save_output(book_title: str, image_map: dict[str, bytes], articles: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Save images
    for safe_name, data in image_map.items():
        img_path = IMAGES_DIR / safe_name
        counter = 1
        while img_path.exists():
            stem = img_path.stem
            suffix = img_path.suffix if "." in safe_name else ""
            img_path = IMAGES_DIR / f"{stem}_{counter}{suffix}"
            counter += 1
        img_path.write_bytes(data)

    # Extract date from book title
    date_match = re.search(r"\((\d{2}\s+\w{3}\s+\d{4})\)", book_title)
    date_str = date_match.group(1) if date_match else "Unknown date"

    # Build combined Markdown
    parts: list[str] = [
        f"# {book_title}",
        "",
        f"*Extracted on {date_str}*",
        "",
        "---",
        "",
    ]

    for article in articles:
        md = to_markdown(article)
        md = re.sub(r"\n{3,}", "\n\n", md)  # collapse excess blank lines
        parts.append(md)
        parts.append("---")
        parts.append("")

    output_file = OUTPUT_DIR / "extracted_articles.md"
    output_file.write_text("\n".join(parts), encoding="utf-8")

    print(f"  Written: {output_file}")
    print(f"  Images:  {len(image_map)} files in {IMAGES_DIR}")

    # Render HTML
    html_path = render_html(book_title, articles, image_map)
    print(f"  HTML:    {html_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("WSJ EPUB Reader")
    print("=" * 60)

    # Step 1: Find EPUB
    epub_path = find_epub()
    if epub_path is None:
        print(f"ERROR: No .epub file found in {BOOKS_DIR}")
        print("Place a WSJ EPUB file in the books/ folder and run again.")
        return

    print(f"\n[1/3] Found EPUB: {epub_path.name}")

    # Step 2: Extract content
    print("[2/3] Extracting articles...")
    book_title, image_map, articles = read_epub(str(epub_path))
    print(f"  Book title : {book_title}")
    print(f"  Articles   : {len(articles)}")
    print(f"  Images     : {len(image_map)}")

    ContinuationResolver().resolve(articles)
    topic_filter = TopicFilter()
    candidates = topic_filter.filter_articles(articles)
    ResearchPicks().enrich(candidates)
    topic_filter.write_reports(candidates, OUTPUT_DIR)
    topic_filter.print_stats()

    # Step 2b: AI analysis
    print('[2b/3] Running AI analysis...')
    config = AIConfig(enabled=True)
    analyze_articles(candidates, config)
    print(f'  Analysis complete for {len(candidates)} candidate articles')

    # Step 3: Save output
    print("[3/3] Saving to output/...")
    save_output(book_title, image_map, articles)

    print("\nDone!")



# ---------------------------------------------------------------------------
# HTML rendering (standalone — does not modify existing pipeline)
# ---------------------------------------------------------------------------

def _build_html(book_title: str, date_str: str, articles: list[dict], image_map: dict[str, bytes]) -> str:
    """Build a complete HTML page from parsed article data."""

    # Build TOC entries
    toc_entries = ""
    for idx, art in enumerate(articles, start=1):
        title = art["title"] if art["title"] else "Untitled"
        picks = art.get("research_picks") if isinstance(art.get("research_picks"), dict) else {}
        rating = html.escape(str(picks.get("rating", "")))
        read_time = html.escape(str(picks.get("estimated_read_time", "")))
        companies = picks.get("companies", [])[:3]
        topics = picks.get("sectors", [])[:1]
        company_buttons = " ".join(f'<button class="toc-filter" data-company="{html.escape(str(c), quote=True)}">{html.escape(str(c))}</button>' for c in companies)
        topic_buttons = " ".join(f'<button class="toc-filter" data-topic="{html.escape(str(t), quote=True)}">{html.escape(str(t))}</button>' for t in topics)
        toc_entries += f'<li class="toc-entry" data-article-index="{idx}"><a href="#article-{idx}">{idx}. {html.escape(title)}</a> <span class="toc-rating">{rating}</span> <span class="toc-time">{read_time}</span> <span class="toc-tags">{company_buttons} {topic_buttons}</span> <span class="toc-state">□ ☆</span></li>\n'

    # Build article sections
    article_sections = ""
    for idx, art in enumerate(articles, start=1):
        title = art["title"] if art["title"] else "Untitled"
        source = art.get("_source", "")

        # Heading
        picks = art.get("research_picks") if isinstance(art.get("research_picks"), dict) else {}
        rating = picks.get("rating", "")
        section = f'<section id="article-{idx}" class="article" data-rating="{html.escape(str(rating), quote=True)}" data-article-index="{idx}">\n'
        section += '<div class="article-tools"><button class="complete-btn" type="button">□</button><button class="bookmark-btn" type="button">☆</button></div>\n'
        section += f'<h2>{title}</h2>\n'

        # Source filename (small grey text)
        if source:
            section += f'<p class="source">Source: {source}</p>\n'

        # Byline
        if art["byline"]:
            section += f'<p class="byline">By {art["byline"]}</p>\n'

        # Subtitle
        if art["subtitle"]:
            section += f'<p class="subtitle"><strong>{art["subtitle"]}</strong></p>\n'

        # Annotation
        if art["annotation"]:
            section += f'<blockquote class="annotation">{art["annotation"]}</blockquote>\n'
        picks = art.get("research_picks")
        if isinstance(picks, dict):
            section += '<div class="research-picks">\n'
            section += f'<p class="analysis-stars">{html.escape(str(picks.get("rating", "")))}</p>\n'
            section += f'<p><strong>Estimated reading time:</strong> {html.escape(str(picks.get("estimated_read_time", "")))}</p>\n'
            if picks.get("companies"):
                section += f'<p><strong>Companies:</strong> {html.escape(", ".join(picks["companies"]))}</p>\n'
            if picks.get("sectors"):
                section += f'<p><strong>Sectors:</strong> {html.escape(", ".join(picks["sectors"]))}</p>\n'
            for label in ("why_it_matters", "market_impact"):
                values = picks.get(label, [])
                if values:
                    section += f'<p><strong>{"Why it matters" if label == "why_it_matters" else "Market impact"}</strong></p><ul>\n'
                    section += "".join(f'<li>{html.escape(str(value))}</li>\n' for value in values[:3]) + '</ul>\n'
            section += '</div>\n'
        # Analysis
        analysis = art.get("analysis")
        if isinstance(analysis, dict):
            try:
                relevance = max(0, min(5, int(analysis.get("investment_relevance", 0))))
            except (ValueError, TypeError):
                relevance = 0

            summary = analysis.get("summary", "")
            stars = "★" * relevance + "☆" * (5 - relevance)

            section += '<div class="analysis-block">\n'
            section += f'<p class="analysis-stars">{stars}</p>\n'
            if summary:
                section += '<p class="analysis-summary-label">Summary</p>\n'
                section += f'<p class="analysis-summary">{html.escape(summary)}</p>\n'
            section += '</div>\n'

# Paragraphs
        paragraphs = art["paragraphs"]
        index = 0
        while index < len(paragraphs):
            para = paragraphs[index]
            text = para["text"] if isinstance(para, dict) else para
            if text == "◆":
                bullets = []
                while index < len(paragraphs):
                    item = paragraphs[index]
                    item_text = item["text"] if isinstance(item, dict) else item
                    if item_text != "◆":
                        break
                    bullets.append(item_text)
                    index += 1
                section += "<ul>\n" + "".join(f"<li>{html.escape(item)}</li>\n" for item in bullets) + "</ul>\n"
                continue
            tag = "h3" if (
                isinstance(para, dict) and para.get("type") == "section_heading"
            ) or text in {"Business & Finance", "Worldwide"} else "p"
            section += f'<{tag}>{html.escape(text)}</{tag}>\n'
            index += 1

        # Images
        for img in art["images"]:
            caption = img.get("caption") or img.get("alt") or "[Image]"
            section += (
                f'<figure><img loading="lazy" decoding="async" '
                f'src="images/{html.escape(img["src"], quote=True)}" '
                f'alt="{html.escape(img.get("alt", ""), quote=True)}">'
                f'<figcaption>{html.escape(caption)}</figcaption></figure>\n'
            )

        # Back to contents link
        section += '<p class="back-link"><a href="#toc">Back to Contents</a></p>\n'
        section += '<hr>\n'
        section += '</section>\n'

        article_sections += section

    html_output = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{book_title} — Daily Reader</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: Georgia, 'Times New Roman', Times, serif;
    line-height: 1.6;
    color: #1a1a1a;
    background: #fafafa;
    padding: 1rem;
  }}
  .container {{
    max-width: 720px;
    margin: 0 auto;
    background: #fff;
    padding: 2rem 2.5rem;
    border: 1px solid #ddd;
    border-radius: 4px;
  }}
  h1.page-title {{
    font-size: 1.4rem;
    margin-bottom: 0.25rem;
    color: #111;
  }}
  p.date-line {{
    font-size: 0.85rem;
    color: #666;
    margin-bottom: 2rem;
    font-style: italic;
  }}
  #toc {{
    margin-bottom: 2.5rem;
    padding: 1rem 1.5rem;
    background: #f5f5f5;
    border-left: 3px solid #333;
  }}
  #toc h2 {{
    font-family: Arial, Helvetica, sans-serif;
    font-size: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.75rem;
    color: #333;
  }}
  #toc ol {{
    padding-left: 1.5rem;
  }}
  #toc li {{
    font-family: Arial, Helvetica, sans-serif;
    font-size: 0.9rem;
    margin-bottom: 0.3rem;
  }}
  #toc a {{
    color: #1a5276;
    text-decoration: none;
  }}
  #toc a:hover {{
    text-decoration: underline;
  }}
  section {{
    margin-bottom: 2rem;
  }}
  section h2 {{
    font-size: 1.3rem;
    margin-bottom: 0.5rem;
  }}
  p.byline {{
    font-style: italic;
    color: #555;
    font-size: 0.9rem;
    margin-bottom: 0.75rem;
  }}
  p.source {{
    font-size: 0.75rem;
    color: #999;
    margin-bottom: 0.5rem;
  }}
  p.subtitle {{
    font-size: 1rem;
    color: #333;
    margin-bottom: 0.75rem;
  }}
  blockquote.annotation {{
    border-left: 3px solid #ccc;
    padding-left: 1rem;
    margin-bottom: 1rem;
    color: #555;
    font-style: italic;
  }}
  p {{
    margin-bottom: 1rem;
    text-align: justify;
  }}
  figure {{
    margin: 1.5rem 0;
    text-align: center;
  }}
  figure img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
  }}
  figcaption {{
    font-size: 0.8rem;
    color: #777;
    margin-top: 0.25rem;
  }}
  .analysis-block {{
    margin: 1rem 0;
    padding: 0.75rem 1rem;
    background: #f8fafc;
    border-left: 4px solid #2563eb;
    border-radius: 6px;
  }}
  .analysis-stars {{
    color: #f59e0b;
    font-size: 1.1rem;
    margin: 0 0 0.5rem;
  }}
  .analysis-summary-label {{
    font-size: 0.85rem;
    font-weight: 600;
    color: #475569;
    margin: 0 0 0.25rem;
  }}
  .analysis-summary {{
    font-size: 0.9rem;
    color: #333;
    line-height: 1.5;
    margin: 0;
  }}

  hr {{
    border: none;
    border-top: 1px solid #ddd;
    margin: 1.5rem 0;
  }}
  p.back-link {{
    font-size: 0.8rem;
    margin-top: 0.5rem;
  }}
  p.back-link a {{
    color: #1a5276;
    text-decoration: none;
  }}
  p.back-link a:hover {{
    text-decoration: underline;
  }}
  footer {{
    text-align: center;
    font-size: 0.75rem;
    color: #999;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid #eee;
  }}
  .reading-toolbar {{ display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; margin:.75rem 0 1.25rem; }}
  .reading-toolbar button, .article-tools button {{ cursor:pointer; border:1px solid #cbd5e1; background:#fff; border-radius:4px; padding:.35rem .6rem; }}
  .reading-toolbar button.active {{ background:#1a5276; color:#fff; }}
  #progress {{ margin-left:auto; color:#64748b; font-size:.85rem; }}
  .article {{ position:relative; }}
  .article-tools {{ position:absolute; right:0; top:0; display:flex; gap:.25rem; }}
  .article-tools button {{ border:0; font-size:1.2rem; padding:.1rem .3rem; }}
  .article.bookmarked .bookmark-btn {{ color:#d97706; }}
  .article.completed .complete-btn {{ color:#15803d; }}
  .article.research-collapsed .research-picks {{ display:none; }}
  .toc-entry {{ margin:.45rem 0; }}
  .toc-rating {{ color:#d97706; }}
  .toc-time {{ color:#64748b; font-size:.85rem; }}
  .toc-filter {{ border:0; background:#eef2ff; color:#334155; border-radius:3px; cursor:pointer; padding:.15rem .3rem; margin:.1rem; }}
  .toc-entry.completed .toc-state {{ color:#15803d; }}
  .toc-entry.bookmarked .toc-state {{ color:#d97706; }}
  @media (max-width: 600px) {{
    body {{ padding: 0; }}
    .container {{
      padding: 1rem 1rem;
      border: none;
      border-radius: 0;
    }}
  }}
</style>
</head>
<body>
<div class="container">
  <h1 class="page-title">{book_title}</h1>
  <p class="date-line">Extracted on {date_str} — Generated by WSJReader</p>

  <nav id="toc">
    <h2>Table of Contents</h2>
    <div class="reading-toolbar"><button type="button" data-mode="essentials">Today's Essentials</button><button type="button" data-mode="research">Today's Research</button><button type="button" data-mode="full">Full Issue</button><button type="button" data-mode="bookmarks">My Picks</button><span id="progress"></span></div>
    <ol>
{toc_entries}    </ol>
  </nav>

{article_sections}

  <footer>
    <p>WSJReader — EPUB to HTML</p>
  </footer>
</div>
<script>
(function () {{
  const storageKey = 'researchreader-reading-state';
  const state = JSON.parse(localStorage.getItem(storageKey) || '{{"completed":{{}},"bookmarks":{{}},"collapsed":{{}}}}');
  const articles = [...document.querySelectorAll('.article')];
  const progress = document.getElementById('progress');
  function save() {{ localStorage.setItem(storageKey, JSON.stringify(state)); }}
  function updateProgress() {{ const shown = articles.filter(a => !a.hidden); progress.textContent = `${{shown.filter(a => state.completed[a.dataset.articleIndex]).length}} / ${{shown.length}} articles completed`; }}
  function apply(mode) {{
    document.querySelectorAll('[data-mode]').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
    articles.forEach(a => {{ const r = a.dataset.rating || ''; const entry = document.querySelector(`.toc-entry[data-article-index="${{a.dataset.articleIndex}}"]`); const company = state.filterCompany; const topic = state.filterTopic; const keepMode = mode === 'full' || (mode === 'essentials' && (r.startsWith('★★★★★') || r.startsWith('★★★★☆'))) || (mode === 'research' && r.length >= 3 && !r.startsWith('★☆☆☆☆') && !r.startsWith('★★☆☆☆')) || (mode === 'bookmarks' && state.bookmarks[a.dataset.articleIndex]); const keepCompany = !company || entry?.querySelector(`[data-company="${{CSS.escape(company)}}"]`); const keepTopic = !topic || entry?.querySelector(`[data-topic="${{CSS.escape(topic)}}"]`); a.hidden = !(keepMode && keepCompany && keepTopic); if (entry) entry.hidden = a.hidden; }});
    state.mode = mode; save(); updateProgress();
  }}
  articles.forEach(a => {{ const id = a.dataset.articleIndex; const entry = document.querySelector(`.toc-entry[data-article-index="${{id}}"]`); const refreshState = () => {{ if (entry) {{ entry.classList.toggle('completed', !!state.completed[id]); entry.classList.toggle('bookmarked', !!state.bookmarks[id]); entry.querySelector('.toc-state').textContent = `${{state.completed[id] ? '✓' : '□'}} ${{state.bookmarks[id] ? '★' : '☆'}}`; }} }}; if (state.completed[id]) a.classList.add('completed'); if (state.bookmarks[id]) a.classList.add('bookmarked'); if (state.collapsed[id]) a.classList.add('research-collapsed'); refreshState(); a.querySelector('.complete-btn').onclick = () => {{ state.completed[id] = !state.completed[id]; a.classList.toggle('completed', state.completed[id]); refreshState(); save(); updateProgress(); }}; a.querySelector('.bookmark-btn').onclick = () => {{ state.bookmarks[id] = !state.bookmarks[id]; a.classList.toggle('bookmarked', state.bookmarks[id]); refreshState(); save(); }}; const card = a.querySelector('.research-picks'); if (card) card.onclick = () => {{ state.collapsed[id] = !state.collapsed[id]; a.classList.toggle('research-collapsed', state.collapsed[id]); save(); }}; }});
  document.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => apply(b.dataset.mode));
  document.querySelectorAll('.toc-filter').forEach(b => b.onclick = e => {{ e.preventDefault(); const isCompany = b.dataset.company !== undefined; const value = isCompany ? b.dataset.company : b.dataset.topic; const key = isCompany ? 'filterCompany' : 'filterTopic'; state[key] = state[key] === value ? '' : value; apply(state.mode || 'full'); }});
  let current = -1; function move(step) {{ const shown = articles.filter(a => !a.hidden); current = Math.max(0, Math.min(shown.length - 1, current + step)); shown[current]?.scrollIntoView({{behavior:'smooth', block:'start'}}); }}
  document.addEventListener('keydown', e => {{ if (['INPUT','TEXTAREA','BUTTON'].includes(document.activeElement.tagName)) return; if (e.key === 'j') move(1); if (e.key === 'k') move(-1); if (e.key === 'b' && current >= 0) articles.filter(a => !a.hidden)[current]?.querySelector('.bookmark-btn').click(); if (e.key === 'f') apply(state.mode === 'essentials' ? 'research' : state.mode === 'research' ? 'full' : 'essentials'); }});
  articles.forEach(a => {{ const entry = document.querySelector(`.toc-entry[data-article-index="${{a.dataset.articleIndex}}"]`); const id = a.dataset.articleIndex; if (entry) {{ entry.classList.toggle('completed', !!state.completed[id]); entry.classList.toggle('bookmarked', !!state.bookmarks[id]); entry.querySelector('.toc-state').textContent = `${{state.completed[id] ? '✓' : '□'}} ${{state.bookmarks[id] ? '★' : '☆'}}`; }} }});
  apply(state.mode || 'essentials');
}})();
</script>
</body>
</html>"""
    return html_output


def render_html(book_title: str, articles: list[dict], image_map: dict[str, bytes]) -> Path:
    """Render articles to output/daily.html and return the output path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Extract date from book title
    date_match = re.search(r"\((\d{2}\s+\w{3}\s+\d{4})\)", book_title)
    date_str = date_match.group(1) if date_match else "Unknown date"

    html = _build_html(book_title, date_str, articles, image_map)
    output_file = OUTPUT_DIR / "daily.html"
    output_file.write_text(html, encoding="utf-8")
    return output_file
if __name__ == "__main__":
    main()
