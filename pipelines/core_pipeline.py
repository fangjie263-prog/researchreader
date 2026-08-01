"""AI-free EPUB to normalized Article artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import wsj_reader
from article_factory import ArticleFactory
from continuation import ContinuationMerger, ContinuationResolver
from topic_filter import TopicFilter
from workspace import WorkspaceManager


class CorePipeline:
    def run(self, book_path: str | Path, output_root: str | Path | None = None) -> Path:
        book = Path(book_path)
        root = Path(output_root or wsj_reader.OUTPUT_DIR)
        root = WorkspaceManager.create(root, book.stem, "")
        title, image_map, articles = wsj_reader.read_epub(str(book))
        links = ContinuationResolver().resolve(articles)
        ContinuationMerger().merge(articles, links)
        articles = TopicFilter().filter_articles(articles)
        article_objects = [ArticleFactory.from_dict(article) for article in articles]
        records = [ArticleFactory.to_dict(article) for article in article_objects]
        payload = {
            "schema_version": "2.0", "publication": title,
            "issue_date": "", "generated_at": datetime.now(timezone.utc).isoformat(),
            "articles": records,
        }
        json_path = root / "articles.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest = WorkspaceManager.load(root)
        manifest["article_count"] = len(records)
        (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        old_output, old_images = wsj_reader.OUTPUT_DIR, wsj_reader.IMAGES_DIR
        try:
            wsj_reader.OUTPUT_DIR, wsj_reader.IMAGES_DIR = root, root / "images"
            wsj_reader.save_output(title, image_map, articles)
        finally:
            wsj_reader.OUTPUT_DIR, wsj_reader.IMAGES_DIR = old_output, old_images
        print("Core Pipeline completed.")
        print(f"Articles: {len(records)}")
        print(f"JSON: {json_path}")
        print("No AI used.")
        return json_path
