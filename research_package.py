"""Build a single-article bilingual research package."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from article_translator import ArticleTranslator

ROOT = Path(__file__).resolve().parent
RECOMMENDATIONS = ROOT / "output" / "reading_recommendations.json"


class ResearchPackage:
    def __init__(self, translator=None, output_root=ROOT / "output"):
        self.translator = translator or ArticleTranslator()
        self.output_root = Path(output_root)

    def create(self, article_id: str) -> Path:
        result = self.translator.translate(article_id)
        package_dir = self.output_root / "package" / article_id
        package_dir.mkdir(parents=True, exist_ok=True)
        for name in ("article.md", "article_zh.md"):
            shutil.copyfile(result.output_directory / name, package_dir / name)
        config = getattr(getattr(self.translator, "service", None), "_config", None)
        metadata = {
            "article_id": result.article.article_id,
            "title": result.article.title,
            "source_document": result.article.source_document,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "translation_provider": getattr(config, "base_url", None),
            "translation_model": getattr(config, "model", None),
        }
        (package_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        original = (package_dir / "article.md").read_text(encoding="utf-8")
        chinese = (package_dir / "article_zh.md").read_text(encoding="utf-8")
        bilingual = f"# {result.article.title}\n\nSource\n\n{result.article.source_document}\n\n## Original\n\n{original}\n\n## 中文翻译\n\n{chinese}\n"
        (package_dir / "bilingual.md").write_text(bilingual, encoding="utf-8")
        return package_dir

    def create_many(self, article_ids: list[str]) -> tuple[list[dict], list[dict]]:
        successes: list[dict] = []
        failures: list[dict] = []
        for article_id in article_ids:
            try:
                package_dir = self.create(article_id)
                metadata = json.loads((package_dir / "metadata.json").read_text(encoding="utf-8"))
                successes.append({"article_id": article_id, "title": metadata["title"]})
                print(f"Success: {article_id}")
            except Exception as exc:
                failures.append({"article_id": article_id, "error": str(exc)})
                print(f"Skipped: {article_id}")

        summary = ["# Research Package", "", f"Generated:", datetime.now(timezone.utc).isoformat(), "", "Articles:", ""]
        for item in successes:
            summary.extend([f"✓ {item['article_id']}", "", "Title:", item["title"], ""])
        summary.extend(["Count:", str(len(successes)), ""])
        (self.output_root / "package" / "package_summary.md").parent.mkdir(parents=True, exist_ok=True)
        (self.output_root / "package" / "package_summary.md").write_text("\n".join(summary), encoding="utf-8")
        return successes, failures

    @staticmethod
    def select_top(path: Path, top: int) -> list[str]:
        if not path.is_file():
            raise FileNotFoundError("reading_recommendations.json not found.")
        records = json.loads(path.read_text(encoding="utf-8"))
        ordered = sorted(enumerate(records), key=lambda item: (-item[1].get("priority", 0), item[0]))
        return [record["article_id"] for _, record in ordered[:top]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create research packages")
    parser.add_argument("article_id", nargs="*")
    parser.add_argument("--top", type=int)
    args = parser.parse_args()
    if args.top is not None:
        if args.top < 0:
            print("ERROR: --top must be non-negative")
            return 1
        try:
            article_ids = ResearchPackage.select_top(RECOMMENDATIONS, args.top)
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
            print(str(exc))
            return 1
        print("Selected:")
        for article_id in article_ids:
            print(article_id)
    elif args.article_id:
        article_ids = args.article_id
    else:
        parser.error("provide article_id or --top")
    successes, failures = ResearchPackage().create_many(article_ids)
    print("Research Package completed.")
    print(f"Success: {len(successes)}")
    print(f"Failed: {len(failures)}")
    print(f"Output: {ROOT / 'output' / 'package'}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
