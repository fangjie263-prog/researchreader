"""Translate extracted articles through the existing AIService pipeline."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from ai_config import AIServiceConfig
from ai_service import AIService
from article_extractor import ArticleContent, ArticleExtractor
from article_locator import ArticleLocator


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = ROOT / "output"


class ArticleTranslationError(RuntimeError):
    """Raised when the existing translation service cannot translate an article."""


@dataclass
class ArticleTranslationResult:
    article: ArticleContent
    translated_content: str
    output_directory: Path


class ArticleTranslator:
    def __init__(
        self,
        locator: ArticleLocator | None = None,
        extractor: ArticleExtractor | None = None,
        service: AIService | None = None,
        output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    ) -> None:
        self.locator = locator or ArticleLocator()
        self.extractor = extractor or ArticleExtractor(self.locator)
        self.service = service or self._configured_service()
        self.output_root = Path(output_root)

    @staticmethod
    def _configured_service() -> AIService:
        config = AIServiceConfig.from_env()
        if not config.is_active:
            raise ArticleTranslationError("AI is not configured. Run 'python ai_setup.py setup'.")
        return AIService(config)

    def translate(self, article_id: str) -> ArticleTranslationResult:
        article = self.extractor.extract(article_id)
        try:
            translated = self.service.translate_article({
                "title": article.title,
                "paragraphs": article.content.splitlines(),
            })
            paragraphs = translated.get("paragraphs")
            if not isinstance(paragraphs, list) or not paragraphs:
                raise ArticleTranslationError("TranslationPipeline returned no translated paragraphs")
            translated_content = "\n\n".join(str(paragraph).strip() for paragraph in paragraphs if str(paragraph).strip())
            if not translated_content:
                raise ArticleTranslationError("TranslationPipeline returned an empty translation")
        except ArticleTranslationError:
            raise
        except Exception as exc:
            raise ArticleTranslationError(f"Translation failed: {exc}") from exc

        output_directory = self.output_root / "translated_articles" / article.article_id
        output_directory.mkdir(parents=True, exist_ok=True)
        (output_directory / "article.md").write_text(
            f"# {article.title}\n\n{article.content}\n", encoding="utf-8"
        )
        translated_title = str(translated.get("title") or article.title).strip()
        (output_directory / "article_zh.md").write_text(
            f"# {translated_title}\n\n{translated_content}\n", encoding="utf-8"
        )
        return ArticleTranslationResult(article, translated_content, output_directory)


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate recommended articles sequentially")
    parser.add_argument("article_ids", nargs="+", help="article_id values such as article_001")
    args = parser.parse_args()
    try:
        translator = ArticleTranslator()
    except ArticleTranslationError as exc:
        print(f"ERROR: {exc}")
        return 1
    failed = False
    for article_id in args.article_ids:
        try:
            result = translator.translate(article_id)
            print(f"Translated: {article_id}")
            print(f"Output: {result.output_directory}")
        except Exception as exc:
            failed = True
            print(f"ERROR [{article_id}]: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
