"""AI workflow consuming only the Core Pipeline articles.json boundary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_config import AIServiceConfig
from ai_service import AIService, AIServiceError
from workspace import WorkspaceManager


class AIPipeline:
    def run(self, articles_json: str | Path, recommend: bool = False, summary: bool = False, package: bool = False) -> Path:
        path = Path(articles_json)
        if path.is_dir() and (path / "manifest.json").is_file():
            manifest = WorkspaceManager.load(path)
            path = path / manifest["files"]["articles"]
        data = json.loads(path.read_text(encoding="utf-8"))
        articles = data.get("articles", data) if isinstance(data, dict) else data
        if not isinstance(articles, list):
            raise ValueError("articles.json must contain an articles array")
        if not any((recommend, summary, package)):
            recommend = True
        config = AIServiceConfig.from_env()
        if not config.is_active:
            raise RuntimeError("AI is not configured")
        service = AIService(config)
        results = []
        if recommend:
            for article in articles:
                text = "\n\n".join([article.get("title", "")] + [str(p) for p in article.get("paragraphs", [])[:10]])
                try:
                    raw = service.screen_article(article.get("title", ""), text, "")
                    if raw.get("recommend"):
                        results.append({**article, **raw})
                except (AIServiceError, ValueError) as exc:
                    print(f"Skipped {article.get('title', '')}: {exc}")
            output_dir = path.parent / "recommendations"
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / "reading_recommendations.json"
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return output
        return path.parent / "reading_recommendations.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI workflows on articles.json")
    parser.add_argument("articles_json", type=Path)
    parser.add_argument("--recommend", action="store_true")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--package", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    try:
        output = AIPipeline().run(args.articles_json, args.recommend or args.all, args.summary or args.all, args.package or args.all)
        print(f"AI Pipeline completed.\nOutput: {output}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
