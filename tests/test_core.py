import json
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from hkej_to_html import _parse_json, build_html, parse_input
from pdf_queue import _to_markdown
from pdf_reader import _deduplicate_and_join_pages, _render_html
from topic_manager import topic_context, save_topics
from research_digest import _matches_topics, build_json_records, build_report, write_json_report
from article_locator import ArticleLocator, ArticleNotFound
from article_extractor import ArticleContent, ArticleExtractionError, ArticleExtractor
from article_translator import ArticleTranslationError, ArticleTranslator


class PdfCoreTests(unittest.TestCase):
    def test_duplicate_paragraphs_are_removed_and_page_continuation_is_joined(self):
        pages = [
            ["The first half"],
            ["continues here.", "Repeated paragraph"],
            ["Repeated paragraph"],
        ]
        result = _deduplicate_and_join_pages(pages)
        self.assertEqual(result[0], ["The first half continues here."])
        self.assertEqual(result[1], ["Repeated paragraph"])
        self.assertEqual(result[2], [])

    def test_pdf_html_escapes_text_and_contains_page_navigation(self):
        html = _render_html("A < PDF", "book.pdf", [{"_page": 1, "paragraphs": ["x < y"]}])
        self.assertIn("A &lt; PDF", html)
        self.assertIn("x &lt; y", html)
        self.assertIn("#page-1", html)

    def test_pdf_markdown_contains_title_source_and_paragraphs(self):
        markdown = _to_markdown("Book", "book.pdf", [{"title": "Page 1", "paragraphs": ["Text"]}])
        self.assertIn("# Book", markdown)
        self.assertIn("Source: book.pdf", markdown)
        self.assertIn("Text", markdown)


class WsjCoreTests(unittest.TestCase):
    def test_articles_with_same_title_are_merged_and_deduplicated(self):
        from wsj_reader import merge_articles

        result = merge_articles([
            {"title": "Story", "subtitle": "", "byline": "", "paragraphs": ["One", "Two"], "images": []},
            {"title": "Story", "subtitle": "", "byline": "", "paragraphs": ["Two", "Three"], "images": []},
        ])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["paragraphs"], ["One", "Two", "Three"])


class HkejCoreTests(unittest.TestCase):
    def test_json_parser_reads_articles(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "news.json"
            path.write_text(json.dumps({"time": "now", "articles": [{"title": "Title", "content": "Body"}]}), encoding="utf-8")
            metadata, articles = _parse_json(path)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Title")
        self.assertEqual(articles[0]["content"], "Body")

    def test_txt_parser_reads_article_blocks(self):
        content = "抓取时间: now\n\n标题: Title\n链接: https://example.com\n分类: markets\n正文:\nBody\n"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "news.txt"
            path.write_text(content, encoding="utf-8")
            _, articles = parse_input(path)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["content"], "Body")

    def test_html_builder_escapes_article_content(self):
        html = build_html({}, [{"title": "A < B", "url": "", "category": "", "content": "x < y"}], Path("news.txt"))
        self.assertIn("A &lt; B", html)
        self.assertIn("x &lt; y", html)


class AiConfigTests(unittest.TestCase):
    def test_ai_service_is_active_only_with_key_and_base_url(self):
        from ai_config import AIServiceConfig

        with patch.dict(os.environ, {"AI_API_KEY": "key", "AI_BASE_URL": "https://example.test", "AI_MODEL": "model"}, clear=False):
            config = AIServiceConfig.from_env()
        self.assertTrue(config.is_active)

        with patch.dict(os.environ, {"AI_API_KEY": "", "AI_BASE_URL": "https://example.test", "AI_SETTINGS_PATH": "__missing_ai_settings__.json"}, clear=False):
            config = AIServiceConfig.from_env()
        self.assertFalse(config.is_active)

    def test_settings_can_be_saved_and_loaded_without_environment_variables(self):
        from ai_config import AIServiceConfig

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ai_settings.json"
            original = {"AI_SETTINGS_PATH": os.environ.get("AI_SETTINGS_PATH")}
            with patch.dict(os.environ, {"AI_SETTINGS_PATH": str(path), "AI_API_KEY": "", "AI_BASE_URL": "", "AI_MODEL": ""}, clear=False):
                AIServiceConfig(True, "secret", "https://example.test/v1", "model").save(path)
                loaded = AIServiceConfig.from_env()
            self.assertEqual(loaded.api_key, "secret")
            self.assertEqual(loaded.model, "model")

    def test_topic_context_contains_chinese_english_and_related_terms(self):
        context = topic_context([{
            "name_zh": "人工智能",
            "keywords_zh": ["大模型"],
            "keywords_en": ["AI", "LLM"],
            "related_topics": ["云计算"],
        }])
        self.assertIn("人工智能", context)
        self.assertIn("AI", context)
        self.assertIn("云计算", context)

    def test_benchmark_timeout_becomes_failed_result(self):
        from ai_config import AIServiceConfig
        from ai_service import AIService

        service = AIService(AIServiceConfig(True, "key", "https://example.test", "model"))
        with patch.object(AIService, "summarize", side_effect=TimeoutError("timed out")):
            result = service.benchmark_model("slow", timeout=1)
        self.assertEqual(result["status"], "FAILED")
        self.assertIsNone(result["latency"])

    def test_benchmark_http_failure_becomes_failed_result(self):
        from ai_config import AIServiceConfig
        from ai_service import AIService, AIServiceError

        service = AIService(AIServiceConfig(True, "key", "https://example.test", "model"))
        with patch.object(AIService, "summarize", side_effect=AIServiceError("HTTP 500")):
            result = service.benchmark_model("broken", timeout=1)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("HTTP 500", result["error"])

    def test_recommend_model_continues_after_failure_and_sorts_passes(self):
        from ai_config import AIServiceConfig
        from ai_service import AIService

        service = AIService(AIServiceConfig(True, "key", "https://example.test", "model"))
        responses = [
            {"model": "a", "status": "FAILED", "latency": 2.0, "error": "429"},
            {"model": "b", "status": "PASS", "latency": 1.4, "error": ""},
            {"model": "c", "status": "PASS", "latency": 0.8, "error": ""},
        ]
        with patch.object(service, "benchmark_model", side_effect=responses):
            result = service.recommend_model(["a", "b", "c"], timeout=1)
        self.assertEqual(result["recommended"], "c")
        self.assertEqual([item["model"] for item in result["results"]], ["a", "b", "c"])

    def test_recommend_model_continues_if_benchmark_raises(self):
        from ai_config import AIServiceConfig
        from ai_service import AIService

        service = AIService(AIServiceConfig(True, "key", "https://example.test", "model"))
        with patch.object(service, "benchmark_model", side_effect=[RuntimeError("network"), {"model": "b", "status": "PASS", "latency": 0.5, "error": ""}]):
            result = service.recommend_model(["a", "b"], timeout=1)
        self.assertEqual(result["results"][0]["status"], "FAILED")
        self.assertEqual(result["recommended"], "b")

    def test_benchmark_runner_saves_json_and_returns_success_if_any_passes(self):
        from ai_setup import run_benchmark

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "benchmark.json"
            with patch.dict(os.environ, {
                "AI_API_KEY": "key",
                "AI_BASE_URL": "https://api.hcnsec.example/v1",
                "AI_MODEL": "",
                "AI_BENCHMARK_PATH": str(path),
            }, clear=False), patch("ai_setup.AIService.list_models", return_value=[{"id": "a"}, {"id": "b"}]), patch(
                "ai_setup.AIService.benchmark_model",
                side_effect=[{"model": "a", "status": "PASS", "latency": 0.7, "error": ""}, {"model": "b", "status": "FAILED", "latency": 1.2, "error": "500"}],
            ):
                _, code = run_benchmark(timeout=10, top=2, provider="hcnsec")
            self.assertEqual(code, 0)
            report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["provider"], "HCNSEC")
        self.assertEqual(len(report["models"]), 2)

    def test_top_limits_models_and_larger_top_uses_all(self):
        from ai_setup import _select_models

        self.assertEqual(_select_models(["a", "b", "c"], "", "", 2), ["a", "b"])
        self.assertEqual(_select_models(["a", "b", "c"], "", "", 10), ["a", "b", "c"])

    def test_provider_filters_model_ids(self):
        from ai_setup import _select_models

        self.assertEqual(_select_models(["deepseek/one", "qwen/two", "deepseek/three"], "deepseek", "", 10), ["deepseek/one", "deepseek/three"])

    def test_unknown_provider_is_reported_without_traceback(self):
        from ai_setup import test_provider

        output = io.StringIO()
        with patch.dict(os.environ, {"AI_API_KEY": "key", "AI_BASE_URL": "https://api.hcnsec.example/v1", "AI_MODEL": ""}, clear=False), patch(
            "ai_setup.AIService.list_models", return_value=[{"id": "deepseek/one"}]
        ), redirect_stdout(output):
            code = test_provider(provider="unknown-provider", top=5)
        self.assertEqual(code, 1)
        self.assertIn("Unknown provider: unknown-provider", output.getvalue())

    def test_digest_local_filter_matches_expanded_terms(self):
        matches = _matches_topics({"title": "AI chips outlook", "text": "Semiconductor demand"}, ["ai", "semiconductor"])
        self.assertEqual(matches, ["ai", "semiconductor"])

    def test_digest_report_contains_only_recommendation_fields(self):
        markdown, html = build_report([{
            "title": "AI chips",
            "source": "book/extracted_articles.md",
            "priority": 5,
            "reason_zh": "与主题高度相关",
            "reason_en": "Highly relevant",
            "summary_zh": "中文短摘要",
            "summary_en": "Short English summary",
        }])
        self.assertIn("中文短摘要", markdown)
        self.assertIn("Short English summary", html)


    def test_digest_json_records_have_complete_sequential_ids(self):
        results = [{
            "title": "First", "source": "first.md", "priority": 5,
            "matched_topics": ["AI"], "summary_zh": "一", "summary_en": "One",
            "reason_zh": "理由一", "reason_en": "Reason one",
        }, {
            "title": "Second", "source": "second.md", "priority": 3,
            "matched_topics": ["chips"], "summary_zh": "二", "summary_en": "Two",
            "reason_zh": "理由二", "reason_en": "Reason two",
        }]
        required = {
            "article_id", "title", "priority", "matched_topics", "summary_zh",
            "summary_en", "reason_zh", "reason_en", "source_document",
        }
        with tempfile.TemporaryDirectory() as temp:
            path = write_json_report(Path(temp) / "reading_recommendations.json", results)
            records = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([r["article_id"] for r in records], ["article_001", "article_002"])
        self.assertEqual(len({r["article_id"] for r in records}), 2)
        self.assertTrue(all(required <= set(r) for r in records))

    def test_digest_markdown_is_unchanged_when_article_id_is_added(self):
        result = {
            "title": "AI chips", "source": "article.md", "priority": 4,
            "matched_topics": ["AI"], "reason_zh": "相关", "reason_en": "Relevant",
            "summary_zh": "摘要", "summary_en": "Summary",
        }
        before = build_report([result])[0]
        after = build_report([{**result, "article_id": "article_001"}])[0]
        self.assertEqual(before, after)


class ArticleLocatorTests(unittest.TestCase):
    def _write_json(self, temp: str, records: list[dict]) -> Path:
        path = Path(temp) / "reading_recommendations.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        return path

    def _record(self, article_id: str) -> dict:
        return {
            "article_id": article_id,
            "title": f"Title {article_id}",
            "priority": 5,
            "matched_topics": ["AI"],
            "summary_zh": "摘要",
            "summary_en": "Summary",
            "reason_zh": "理由",
            "reason_en": "Reason",
            "source_document": "articles.md",
        }

    def test_locator_returns_requested_article(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_json(temp, [self._record("article_001")])
            article = ArticleLocator(path).get("article_001")
        self.assertEqual(article["title"], "Title article_001")

    def test_locator_raises_article_not_found(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_json(temp, [self._record("article_001")])
            with self.assertRaisesRegex(ArticleNotFound, "article_999"):
                ArticleLocator(path).get("article_999")

    def test_locator_supports_multiple_articles(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_json(temp, [self._record("article_001"), self._record("article_002")])
            locator = ArticleLocator(path)
            self.assertEqual(locator.get("article_001")["article_id"], "article_001")
            self.assertEqual(locator.get("article_002")["article_id"], "article_002")

    def test_locator_rejects_record_with_missing_fields(self):
        record = self._record("article_001")
        del record["source_document"]
        with tempfile.TemporaryDirectory() as temp:
            path = self._write_json(temp, [record])
            with self.assertRaisesRegex(ValueError, "source_document"):
                ArticleLocator(path)


class ArticleExtractorTests(unittest.TestCase):
    def _record(self, article_id: str = "article_001") -> dict:
        return {
            "article_id": article_id, "title": "Target article", "priority": 5,
            "matched_topics": ["AI"], "summary_zh": "摘要", "summary_en": "Summary",
            "reason_zh": "理由", "reason_en": "Reason", "source_document": "source.md",
        }

    def _setup(self, temp: str, record: dict, source: str) -> ArticleExtractor:
        root = Path(temp) / "output"
        root.mkdir()
        (root / "source.md").write_text(source, encoding="utf-8")
        json_path = Path(temp) / "recommendations.json"
        json_path.write_text(json.dumps([record]), encoding="utf-8")
        return ArticleExtractor(ArticleLocator(json_path), root)

    def test_extractor_returns_complete_markdown_article(self):
        with tempfile.TemporaryDirectory() as temp:
            extractor = self._setup(temp, self._record(), "# File\n## Target article\nFirst paragraph.\n\nSecond paragraph.\n## Other\nOther text.")
            content = extractor.extract("article_001")
        self.assertIsInstance(content, ArticleContent)
        self.assertEqual(content.title, "Target article")
        self.assertIn("First paragraph.", content.content)
        self.assertIn("Second paragraph.", content.content)
        self.assertNotIn("Other text.", content.content)

    def test_extractor_reports_missing_body(self):
        with tempfile.TemporaryDirectory() as temp:
            extractor = self._setup(temp, self._record(), "# Other\nOther text.")
            with self.assertRaisesRegex(ArticleExtractionError, "body"):
                extractor.extract("article_001")

    def test_extractor_reports_missing_markdown_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "output"
            root.mkdir()
            record = self._record()
            json_path = Path(temp) / "recommendations.json"
            json_path.write_text(json.dumps([record]), encoding="utf-8")
            with self.assertRaisesRegex(ArticleExtractionError, "source"):
                ArticleExtractor(ArticleLocator(json_path), root).extract("article_001")


    def test_extractor_propagates_locator_not_found(self):
        with tempfile.TemporaryDirectory() as temp:
            extractor = self._setup(temp, self._record(), "## Target article\nBody")
            with self.assertRaisesRegex(ArticleNotFound, "article_999"):
                extractor.extract("article_999")

    def test_extractor_reports_empty_body(self):
        with tempfile.TemporaryDirectory() as temp:
            extractor = self._setup(temp, self._record(), "## Target article\n---\n")
            with self.assertRaisesRegex(ArticleExtractionError, "empty"):
                extractor.extract("article_001")


class ArticleTranslatorTests(unittest.TestCase):
    class FakeService:
        def translate_article(self, article):
            return {"title": "中文标题", "paragraphs": [f"翻译：{p}" for p in article["paragraphs"]]}

    class FailingService:
        def translate_article(self, article):
            raise RuntimeError("provider unavailable")

    def _make_translator(self, temp: str, service=None, article_ids=None):
        article_ids = article_ids or ["article_001"]
        source_root = Path(temp) / "output"
        source_root.mkdir()
        records = []
        for article_id in article_ids:
            source_name = f"{article_id}.md"
            (source_root / source_name).write_text(f"## Title {article_id}\nOriginal body", encoding="utf-8")
            records.append({
                "article_id": article_id, "title": f"Title {article_id}", "priority": 5,
                "matched_topics": ["AI"], "summary_zh": "摘要", "summary_en": "Summary",
                "reason_zh": "理由", "reason_en": "Reason", "source_document": source_name,
            })
        json_path = Path(temp) / "recommendations.json"
        json_path.write_text(json.dumps(records), encoding="utf-8")
        locator = ArticleLocator(json_path)
        return ArticleTranslator(
            locator=locator,
            extractor=ArticleExtractor(locator, source_root),
            service=service or self.FakeService(),
            output_root=source_root,
        )

    def test_translator_generates_original_and_chinese_files(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self._make_translator(temp).translate("article_001")
            output = result.output_directory
            self.assertIn("Original body", (output / "article.md").read_text(encoding="utf-8"))
            self.assertIn("翻译：Original body", (output / "article_zh.md").read_text(encoding="utf-8"))

    def test_translator_handles_multiple_articles_in_order(self):
        with tempfile.TemporaryDirectory() as temp:
            translator = self._make_translator(temp, article_ids=["article_001", "article_002"])
            results = [translator.translate(article_id) for article_id in ["article_001", "article_002"]]
        self.assertEqual([result.article.article_id for result in results], ["article_001", "article_002"])

    def test_translator_reports_missing_body(self):
        with tempfile.TemporaryDirectory() as temp:
            translator = self._make_translator(temp)
            source = Path(temp) / "output" / "article_001.md"
            source.write_text("## Other\nOther body", encoding="utf-8")
            with self.assertRaises(ArticleExtractionError):
                translator.translate("article_001")

    def test_translator_reports_pipeline_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            translator = self._make_translator(temp, service=self.FailingService())
            with self.assertRaisesRegex(ArticleTranslationError, "Translation failed"):
                translator.translate("article_001")

    def test_translator_creates_output_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self._make_translator(temp).translate("article_001")
            self.assertTrue((result.output_directory / "article.md").is_file())
            self.assertTrue((result.output_directory / "article_zh.md").is_file())

if __name__ == "__main__":
    unittest.main()
