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
from topic_filter import TopicFilter
from research_digest import _matches_topics, build_json_records, build_report, write_json_report
from article_locator import ArticleLocator, ArticleNotFound
from article_extractor import ArticleContent, ArticleExtractionError, ArticleExtractor
from article_translator import ArticleTranslationError, ArticleTranslator
from article_merger import ArticleMerger
from continuation import ContinuationLink, ContinuationMerger, ContinuationResolver
from parser_debug import ParserDebugger
from paragraph_trace import ParagraphTracer
from wsj_reader import _register_dom_visit


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


class ArticleMergerTests(unittest.TestCase):
    def test_merges_partial_paragraph_overlap(self):
        merged = ArticleMerger().merge([
            {"title": "Story", "paragraphs": ["ABCDE"]},
            {"title": "Story", "paragraphs": ["CDEFG"]},
        ], emit_log=False)
        self.assertEqual(merged[0]["paragraphs"], ["ABCDEFG"])


class DuplicateReportTests(unittest.TestCase):
    def test_reports_normalized_duplicate_positions(self):
        from duplicate_report import build_report

        report = build_report([{
            "article_id": "article_001",
            "title": "Story",
            "paragraphs": ["First", " Same  text ", "Other", "Same text"],
        }])
        self.assertEqual(report[0]["occurrences"], [1, 3])
        self.assertEqual(report[0]["duplicate_text"], " Same  text ")

    def test_omits_articles_without_duplicates(self):
        from duplicate_report import build_report

        self.assertEqual(build_report([{"title": "Clean", "paragraphs": ["A", "B"]}]), [])

    def test_removes_identical_paragraph_after_merge(self):
        merged = ArticleMerger().merge([
            {"title": "Story", "paragraphs": ["ABCDE"]},
            {"title": "Story", "paragraphs": ["ABCDE"]},
        ], emit_log=False)
        self.assertEqual(merged[0]["paragraphs"], ["ABCDE"])

    def test_keeps_non_overlapping_paragraphs(self):
        merged = ArticleMerger().merge([
            {"title": "Story", "paragraphs": ["ABCDE"]},
            {"title": "Story", "paragraphs": ["FGHI"]},
        ], emit_log=False)
        self.assertEqual(merged[0]["paragraphs"], ["ABCDE", "FGHI"])

    def test_remerging_same_article_does_not_add_text(self):
        first = ArticleMerger().merge([
            {"title": "Story", "paragraphs": ["ABCDE"]},
            {"title": "Story", "paragraphs": ["CDEFG"]},
        ], emit_log=False)[0]
        merged = ArticleMerger().merge([first, {"title": "Story", "paragraphs": ["CDEFG"]}], emit_log=False)
        self.assertEqual(merged[0]["paragraphs"], ["ABCDEFG"])

    def test_merges_articles_with_identical_titles(self):
        merged = ArticleMerger().merge([
            {
                "title": "Apple Earnings",
                "subtitle": "First",
                "author": "Alice",
                "source": "a.md",
                "paragraphs": ["First paragraph."],
                "images": [{"src": "one.png"}],
                "_page": 1,
            },
            {
                "title": "Apple Earnings",
                "subtitle": "Second",
                "author": "Bob",
                "source": "b.md",
                "paragraphs": ["Second paragraph."],
                "images": [{"src": "two.png"}],
                "_page": 2,
            },
        ], emit_log=False)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["paragraphs"], ["First paragraph.", "Second paragraph."])
        self.assertEqual(merged[0]["images"], [{"src": "one.png"}, {"src": "two.png"}])
        self.assertEqual(merged[0]["subtitle"], "First")
        self.assertEqual(merged[0]["author"], "Alice")
        self.assertEqual(merged[0]["source"], "a.md")
        self.assertEqual(merged[0]["_page"], 1)

    def test_keeps_articles_with_different_titles_separate(self):
        merged = ArticleMerger().merge([
            {"title": "Apple", "paragraphs": ["One"], "images": []},
            {"title": "Amazon", "paragraphs": ["Two"], "images": []},
        ], emit_log=False)
        self.assertEqual(len(merged), 2)

    def test_merges_case_insensitive_titles(self):
        merged = ArticleMerger().merge([
            {"title": "Apple", "paragraphs": ["One"], "images": []},
            {"title": "apple", "paragraphs": ["Two"], "images": []},
        ], emit_log=False)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["paragraphs"], ["One", "Two"])

    def test_merges_titles_with_surrounding_spaces(self):
        merged = ArticleMerger().merge([
            {"title": " Apple ", "paragraphs": ["One"], "images": []},
            {"title": "Apple", "paragraphs": ["Two"], "images": []},
        ], emit_log=False)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["paragraphs"], ["One", "Two"])


class ContinuationResolverTests(unittest.TestCase):
    def test_detects_continued_on_marker(self):
        articles = [
            {"article_id": "article_001", "title": "A", "subtitle": "", "paragraphs": ["Continued on A7"], "page_reference": "A1"},
            {"article_id": "article_002", "title": "B", "subtitle": "", "paragraphs": [], "page_reference": "A7"},
        ]
        links = ContinuationResolver().resolve(articles, emit_log=False)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].source_article, "article_001")
        self.assertEqual(links[0].target_article, "article_002")
        self.assertEqual(links[0].page_reference, "A7")

    def test_detects_case_insensitive_marker(self):
        articles = [
            {"article_id": "article_001", "title": "A", "subtitle": "", "paragraphs": ["continued on a7"], "page_reference": "A1"},
            {"article_id": "article_002", "title": "B", "subtitle": "", "paragraphs": [], "page_reference": "A7"},
        ]
        links = ContinuationResolver().resolve(articles, emit_log=False)
        self.assertEqual(len(links), 1)

    def test_detects_continued_from_page_marker(self):
        articles = [
            {"article_id": "article_001", "title": "A", "subtitle": "", "paragraphs": ["Continued from Page C3"], "page_reference": "C1"},
            {"article_id": "article_002", "title": "B", "subtitle": "", "paragraphs": [], "page_reference": "C3"},
        ]
        links = ContinuationResolver().resolve(articles, emit_log=False)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].page_reference, "C3")

    def test_detects_see_page_marker(self):
        articles = [
            {"article_id": "article_001", "title": "A", "subtitle": "", "paragraphs": ["See Page B5"], "page_reference": "B1"},
            {"article_id": "article_002", "title": "B", "subtitle": "", "paragraphs": [], "page_reference": "B5"},
        ]
        links = ContinuationResolver().resolve(articles, emit_log=False)
        self.assertEqual(len(links), 1)

    def test_returns_empty_when_no_marker_exists(self):
        links = ContinuationResolver().resolve([
            {"article_id": "article_001", "title": "A", "subtitle": "", "paragraphs": ["Hello"], "page_reference": "A1"},
        ], emit_log=False)
        self.assertEqual(links, [])

    def test_ignores_missing_target_page(self):
        links = ContinuationResolver().resolve([
            {"article_id": "article_001", "title": "A", "subtitle": "", "paragraphs": ["Continued on A7"], "page_reference": "A1"},
        ], emit_log=False)
        self.assertEqual(links, [])


class ContinuationMergerTests(unittest.TestCase):
    def test_merges_continuation_once(self):
        articles = [
            {"article_id": "article_001", "title": "A", "paragraphs": ["First"], "images": []},
            {"article_id": "article_002", "title": "B", "paragraphs": ["Second"], "images": []},
        ]
        links = [ContinuationResolver().resolve([
            {"article_id": "article_001", "title": "A", "paragraphs": ["Continued on A2"], "page_reference": "A1"},
            {"article_id": "article_002", "title": "B", "paragraphs": [], "page_reference": "A2"},
        ], emit_log=False)[0]]
        ContinuationMerger().merge(articles, links, emit_log=False)
        self.assertEqual(articles[1]["paragraphs"], ["Second", "First"])
        self.assertIn("article_001", articles[1]["merged_article_ids"])
        self.assertEqual(len(articles[1]["paragraphs"]), 2)

    def test_second_merge_is_skipped(self):
        articles = [
            {"article_id": "article_001", "title": "A", "paragraphs": ["First"], "images": []},
            {"article_id": "article_002", "title": "B", "paragraphs": ["Second"], "images": []},
        ]
        links = [ContinuationLink(source_article="article_001", target_article="article_002", page_reference="A2", marker="continued on A2")]
        merger = ContinuationMerger()
        merger.merge(articles, links, emit_log=False)
        merger.merge(articles, links, emit_log=False)
        self.assertEqual(articles[1]["paragraphs"], ["Second", "First"])
        self.assertEqual(articles[1]["images"], [])

    def test_different_continuations_merge_normally(self):
        articles = [
            {"article_id": "article_001", "title": "A", "paragraphs": ["One"], "images": []},
            {"article_id": "article_002", "title": "B", "paragraphs": ["Two"], "images": []},
            {"article_id": "article_003", "title": "C", "paragraphs": ["Three"], "images": []},
        ]
        links = [
            ContinuationLink(source_article="article_001", target_article="article_002", page_reference="A2", marker="continued on A2"),
            ContinuationLink(source_article="article_003", target_article="article_002", page_reference="A2", marker="continued on A2"),
        ]
        ContinuationMerger().merge(articles, links, emit_log=False)
        self.assertEqual(articles[1]["paragraphs"], ["Two", "One", "Three"])

    def test_images_are_not_duplicated_by_double_merge(self):
        articles = [
            {"article_id": "article_001", "title": "A", "paragraphs": ["One"], "images": [{"src": "x.png"}]},
            {"article_id": "article_002", "title": "B", "paragraphs": ["Two"], "images": []},
        ]
        link = ContinuationLink(source_article="article_001", target_article="article_002", page_reference="A2", marker="continued on A2")
        merger = ContinuationMerger()
        merger.merge(articles, [link], emit_log=False)
        merger.merge(articles, [link], emit_log=False)
        self.assertEqual(articles[1]["images"], [{"src": "x.png"}])


class ParserDebuggerTests(unittest.TestCase):
    def test_reports_untitled_and_duplicate_and_empty_body(self):
        debugger = ParserDebugger()
        report = debugger.analyze([
            {"title": "", "subtitle": "", "byline": "", "paragraphs": [], "images": []},
            {"title": "Same", "subtitle": "", "byline": "", "paragraphs": ["Only one"], "images": []},
            {"title": "Same", "subtitle": "", "byline": "", "paragraphs": ["More"], "images": []},
        ])
        self.assertEqual(report["summary"]["articles"], 3)
        self.assertEqual(report["summary"]["untitled"], 1)
        self.assertEqual(report["summary"]["duplicate_titles"], 1)
        self.assertEqual(report["articles"][0]["warnings"], ["Article without title.", "Article without body."])

    def test_writes_parser_debug_json(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "parser_debug.json"
            report = ParserDebugger().dump([
                {"title": "A", "subtitle": "", "byline": "", "paragraphs": ["Body"], "images": []}
            ], target)
            self.assertTrue(target.is_file())
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["summary"]["articles"], 1)
            self.assertEqual(report["summary"]["articles"], 1)

    def test_detects_possible_continuation(self):
        report = ParserDebugger().analyze([
            {"title": "A", "subtitle": "", "byline": "", "paragraphs": ["The meeting focused on AI chips."], "images": []},
            {"title": "B", "subtitle": "", "byline": "", "paragraphs": ["AI chips remained the focus."], "images": []},
        ])
        self.assertGreaterEqual(report["summary"]["possible_continuations"], 1)


class ParagraphTracerTests(unittest.TestCase):
    def test_hash_deduplicates_repeated_paragraphs(self):
        report = ParagraphTracer().trace([
            {"title": "A", "paragraphs": ["Alpha", "Alpha", "Beta"], "images": []}
        ])
        article = report["articles"][0]
        self.assertEqual(article["paragraphs"], 3)
        self.assertEqual(article["unique"], 2)
        self.assertEqual(report["summary"]["duplicate_paragraph_count"], 1)

    def test_duplicate_indexes_are_reported(self):
        report = ParagraphTracer().trace([
            {"title": "A", "paragraphs": ["Alpha", "Beta", "Alpha"], "images": []}
        ])
        duplicates = report["articles"][0]["duplicates"]
        self.assertEqual(duplicates[0]["first_index"], 1)
        self.assertEqual(duplicates[0]["duplicate_indexes"], [3])

    def test_writes_json_output(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "paragraph_trace.json"
            report = ParagraphTracer().trace([
                {"title": "A", "paragraphs": ["Alpha"], "images": []}
            ], target)
            self.assertTrue(target.is_file())
            data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["articles"], 1)
        self.assertEqual(report["summary"]["articles"], 1)

    def test_no_duplicate_article_is_reported_cleanly(self):
        report = ParagraphTracer().trace([
            {"title": "A", "paragraphs": ["Alpha", "Beta"], "images": []}
        ])
        self.assertEqual(report["summary"]["articles_with_duplicate_paragraphs"], 0)
        self.assertEqual(report["articles"][0]["duplicates"], [])


class DomGuardTests(unittest.TestCase):
    def test_same_dom_node_is_detected_on_second_visit(self):
        seen: set[int] = set()
        node = object()
        duplicate1, node_id1 = _register_dom_visit(seen, node)
        duplicate2, node_id2 = _register_dom_visit(seen, node)
        self.assertFalse(duplicate1)
        self.assertTrue(duplicate2)
        self.assertEqual(node_id1, node_id2)

    def test_different_dom_nodes_are_allowed(self):
        seen: set[int] = set()
        first = object()
        second = object()
        duplicate1, _ = _register_dom_visit(seen, first)
        duplicate2, _ = _register_dom_visit(seen, second)
        self.assertFalse(duplicate1)
        self.assertFalse(duplicate2)


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


class TopicFilterTests(unittest.TestCase):
    def test_topic_filter_scores_and_writes_candidate_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            topics_path = temp_path / "topics.json"
            topics_path.write_text(json.dumps([{
                "name_zh": "人工智能",
                "keywords_zh": ["OpenAI"],
                "keywords_en": ["GPU", "NVIDIA"],
                "related_topics": ["CUDA"],
            }], ensure_ascii=False), encoding="utf-8")
            articles = [
                {
                    "title": "OpenAI GPU race",
                    "subtitle": "NVIDIA CUDA stack",
                    "paragraphs": ["OpenAI and NVIDIA are working on GPU tools."],
                    "source": "story.md",
                },
                {
                    "title": "Sports recap",
                    "paragraphs": ["Golf and travel coverage."],
                    "source": "sports.md",
                },
            ]
            filter_ = TopicFilter(topics_path=topics_path, threshold=15)
            candidates = filter_.filter_articles(articles)
            json_path, md_path = filter_.write_reports(candidates, temp_path)
            self.assertEqual(len(candidates), 1)
            self.assertGreater(candidates[0]["local_score"], 15)
            self.assertIn("OpenAI", candidates[0]["matched_keywords"])
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            self.assertIn("**OpenAI**", md_path.read_text(encoding="utf-8"))

    def test_research_digest_uses_topic_filter_before_ai(self):
        from research_digest import run

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "input.md").write_text("# AI story\nRelevant body", encoding="utf-8")
            fake_candidates = [{
                "title": "AI story",
                "text": "Relevant body",
                "source": "input.md",
                "local_score": 25,
                "matched_keywords": ["AI"],
                "matched_topics": ["人工智能"],
                "preview": "Relevant body",
            }]
            with patch.dict(os.environ, {"AI_API_KEY": "key", "AI_BASE_URL": "https://example.test", "AI_MODEL": "model"}, clear=False), patch(
                "research_digest.collect_candidates", return_value=[{"title": "AI story", "text": "Relevant body", "source": "input.md"}]
            ), patch("research_digest.TopicFilter.filter_articles", return_value=fake_candidates), patch(
                "research_digest.TopicFilter.write_reports"
            ) as write_reports, patch("research_digest.TopicFilter.print_stats"), patch("research_digest.AIService.screen_article", return_value={
                "recommend": True,
                "priority": 5,
                "matched_topics": ["人工智能"],
                "reason_zh": "相关",
                "reason_en": "Relevant",
                "summary_zh": "中文摘要",
                "summary_en": "English summary",
            }) as screen_article:
                md_path, _, count = run(root)
            self.assertEqual(count, 1)
            self.assertEqual(screen_article.call_count, 1)
            self.assertTrue(write_reports.called)
            self.assertTrue(md_path.is_file())


class TopicManagerV2Tests(unittest.TestCase):
    class FakeAliasService:
        def refresh_topic_aliases(self, topics, current_aliases):
            return {
                "aliases": {
                    "人工智能": {
                        "keywords": ["生成式AI", "AI Factory", "market"],
                        "companies": ["OpenAI"],
                        "products": ["GB300"],
                        "technologies": ["Inference Scaling"],
                        "abbreviations": ["GPU"],
                        "updated_at": "2026-07-28",
                        "source": "AI Refresh",
                    }
                }
            }

    def test_refresh_generates_candidate_and_diff_without_overwriting_aliases(self):
        from topic_manager import generate_alias_candidates

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            topics_path = root / "topics.json"
            aliases_path = root / "aliases.json"
            candidate_path = root / "aliases_candidate.json"
            diff_path = root / "aliases.diff.md"
            topics_path.write_text(json.dumps(["人工智能"], ensure_ascii=False), encoding="utf-8")
            aliases_path.write_text(json.dumps({
                "knowledge_version": "2026-01-01",
                "generator": "Test",
                "generator_model": "test-model",
                "generated_at": "2026-01-01T00:00:00",
                "schema_version": 1,
                "topics": {
                    "人工智能": {
                        "keywords": ["OpenCog"],
                        "companies": ["OpenAI"],
                        "products": [],
                        "technologies": [],
                        "abbreviations": [],
                        "updated_at": "2026-01-01",
                        "source": "AI Refresh",
                    }
                }
            }, ensure_ascii=False), encoding="utf-8")
            candidates = generate_alias_candidates(
                self.FakeAliasService(),
                topics_path=topics_path,
                aliases_path=aliases_path,
                candidate_path=candidate_path,
                diff_path=diff_path,
            )
            current = json.loads(aliases_path.read_text(encoding="utf-8"))
            candidate_db = json.loads(candidate_path.read_text(encoding="utf-8"))
            self.assertIn("GB300", candidates["人工智能"]["products"])
            self.assertNotIn("market", candidates["人工智能"]["keywords"])
            self.assertIn("OpenCog", current["topics"]["人工智能"]["keywords"])
            self.assertEqual(candidate_db["schema_version"], 1)
            self.assertIn("topics", candidate_db)
            self.assertTrue(candidate_path.is_file())
            diff = diff_path.read_text(encoding="utf-8")
            self.assertIn("GB300", diff)
            self.assertIn("Reason", diff)
            self.assertIn("OpenCog", diff)

    def test_apply_alias_candidates_accepts_all_or_selected_or_rejects(self):
        from topic_manager import apply_alias_candidates

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            aliases_path = root / "aliases.json"
            candidate_path = root / "aliases_candidate.json"
            aliases_path.write_text(json.dumps({"AI": {"keywords": ["Old"]}}, ensure_ascii=False), encoding="utf-8")
            candidate_path.write_text(json.dumps({
                "AI": {"keywords": ["New"]},
                "Chips": {"companies": ["NVIDIA"]},
            }, ensure_ascii=False), encoding="utf-8")
            with patch("topic_manager.HISTORY_DIR", root / "history"):
                rejected = apply_alias_candidates("reject", candidate_path, aliases_path)
                self.assertEqual(rejected["AI"]["keywords"], ["Old"])
                selected = apply_alias_candidates("selected", candidate_path, aliases_path, ["Chips"])
                self.assertEqual(selected["AI"]["keywords"], ["Old"])
                self.assertEqual(selected["Chips"]["companies"], ["NVIDIA"])
                accepted = apply_alias_candidates("all", candidate_path, aliases_path)
            self.assertEqual(accepted["AI"]["keywords"], ["New"])

    def test_topic_filter_loads_aliases_from_config_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            topics_path = root / "topics.json"
            aliases_path = root / "aliases.json"
            topics_path.write_text(json.dumps(["人工智能"], ensure_ascii=False), encoding="utf-8")
            aliases_path.write_text(json.dumps({
                "knowledge_version": "2026-07-28",
                "generator": "Test",
                "generator_model": "test-model",
                "generated_at": "2026-07-28T00:00:00",
                "schema_version": 1,
                "topics": {
                    "人工智能": {
                        "keywords": ["生成式AI"],
                        "companies": ["OpenAI"],
                        "products": [],
                        "technologies": [],
                        "abbreviations": [],
                        "updated_at": "2026-07-28",
                        "source": "AI Refresh",
                    }
                }
            }, ensure_ascii=False), encoding="utf-8")
            candidates = TopicFilter(topics_path=topics_path, aliases_path=aliases_path).filter_articles([
                {"title": "OpenAI launches new inference tools", "paragraphs": ["Body"]}
            ])
        self.assertEqual(len(candidates), 1)
        self.assertIn("OpenAI", candidates[0]["matched_keywords"])

    def test_topic_filter_keeps_legacy_keyword_topics_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            topics_path = Path(temp) / "topics.json"
            aliases_path = Path(temp) / "aliases.json"
            topics_path.write_text(json.dumps([{
                "name_zh": "Legacy AI",
                "keywords_en": ["OpenAI"],
                "keywords_zh": [],
                "related_topics": [],
            }], ensure_ascii=False), encoding="utf-8")
            aliases_path.write_text("{}", encoding="utf-8")
            candidates = TopicFilter(topics_path=topics_path, aliases_path=aliases_path).filter_articles([
                {"title": "OpenAI news", "paragraphs": ["Body"]}
            ])
        self.assertEqual(len(candidates), 1)

    def test_alias_database_metadata_and_legacy_loading(self):
        from topic_manager import load_alias_database, load_aliases

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aliases.json"
            path.write_text(json.dumps({"AI": {"keywords_en": ["OpenAI"]}}, ensure_ascii=False), encoding="utf-8")
            database = load_alias_database(path)
            aliases = load_aliases(path)
        self.assertEqual(database["schema_version"], 1)
        self.assertIn("knowledge_version", database)
        self.assertEqual(aliases["AI"]["keywords"], ["OpenAI"])

    def test_alias_history_is_created_before_overwrite(self):
        from topic_manager import apply_alias_candidates

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            aliases_path = root / "aliases.json"
            candidate_path = root / "aliases_candidate.json"
            history_dir = root / "history"
            aliases_path.write_text(json.dumps({"AI": {"keywords": ["Old"]}}, ensure_ascii=False), encoding="utf-8")
            candidate_path.write_text(json.dumps({"AI": {"keywords": ["New"]}}, ensure_ascii=False), encoding="utf-8")
            with patch("topic_manager.HISTORY_DIR", history_dir):
                apply_alias_candidates("all", candidate_path, aliases_path)
            history_files = list(history_dir.glob("aliases_*.json"))
            self.assertEqual(len(history_files), 1)
            self.assertIn("Old", history_files[0].read_text(encoding="utf-8"))

    def test_alias_validation_reports_warnings_without_crashing(self):
        from topic_manager import validate_alias_database

        warnings = validate_alias_database({
            "topics": {
                "AI": {
                    "keywords": ["OpenAI", "OpenAI"],
                    "companies": [],
                    "products": [],
                    "abbreviations": ["GPU", "GPU"],
                    "unknown": ["x"],
                }
            }
        })
        self.assertTrue(any("duplicate" in warning for warning in warnings))
        self.assertTrue(any("empty category" in warning for warning in warnings))
        self.assertTrue(any("unknown category" in warning for warning in warnings))

    def test_doctor_interface_writes_reserved_health_report(self):
        from topic_manager import doctor

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            aliases_path = root / "aliases.json"
            report_path = root / "knowledge_health_report.md"
            aliases_path.write_text(json.dumps({"AI": {"keywords": ["OpenAI"]}}, ensure_ascii=False), encoding="utf-8")
            with patch("topic_manager.ALIASES_PATH", aliases_path), patch("topic_manager.KNOWLEDGE_HEALTH_REPORT_PATH", report_path), patch("topic_manager.CONFIG_DIR", root):
                result = doctor()
            self.assertEqual(result, report_path)
            self.assertIn("Knowledge Health Report", report_path.read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
