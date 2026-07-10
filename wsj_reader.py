import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from ebooklib import epub, ITEM_IMAGE, ITEM_DOCUMENT

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
        soup = BeautifulSoup(html, "lxml")

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

    return book_title, image_map, articles


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


def _parse_article(art_div: Tag, base_dir: str, image_lookup: dict, image_map: dict) -> dict:
    """Parse a single <div class=\"art-cnt\"> into structured data."""
    result = {
        "title": "",
        "subtitle": "",
        "annotation": "",
        "byline": "",
        "paragraphs": [],
        "images": [],
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

    # --- Body: walk children of art_div ---
    for child in art_div.children:
        if not isinstance(child, Tag):
            continue

        cls = child.get("class", [])

        # Skip structural wrappers
        if any(c in cls for c in ("art-cnt", "art-header", "legal-header", "art-title-area")):
            continue

        # Regular paragraph
        if child.name == "p":
            text = child.get_text(strip=True)
            if text:
                result["paragraphs"].append(text)

        # Image container
        elif "img-art" in cls:
            img_tag = child.find("img")
            caption_tag = child.find("span", class_="img-text")
            if img_tag:
                src = img_tag.get("src", "")
                alt = img_tag.get("alt", "")
                if src:
                    resolved = _resolve_image(src, base_dir)
                    if resolved:
                        safe = _save_image(resolved, image_lookup, image_map)
                        if safe:
                            result["images"].append({"src": safe, "alt": alt})
                            if caption_tag:
                                result["paragraphs"].append(f"[Image: {caption_tag.get_text(strip=True)}]")

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
        lines.append(para)
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
        toc_entries += f'<li><a href="#article-{idx}">{idx}. {title}</a></li>\n'

    # Build article sections
    article_sections = ""
    for idx, art in enumerate(articles, start=1):
        title = art["title"] if art["title"] else "Untitled"
        source = art.get("_source", "")

        # Heading
        section = f'<section id="article-{idx}">\n'
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

        # Paragraphs
        for para in art["paragraphs"]:
            section += f'<p>{para}</p>\n'

        # Images
        for img in art["images"]:
            section += f'<figure><img src="images/{img["src"]}" alt="{img["alt"]}"><figcaption>[Image]</figcaption></figure>\n'

        # Back to contents link
        section += '<p class="back-link"><a href="#toc">Back to Contents</a></p>\n'
        section += '<hr>\n'
        section += '</section>\n'

        article_sections += section

    html = f"""<!DOCTYPE html>
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
    <ol>
{toc_entries}    </ol>
  </nav>

{article_sections}

  <footer>
    <p>WSJReader — EPUB to HTML</p>
  </footer>
</div>
</body>
</html>"""
    return html


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
