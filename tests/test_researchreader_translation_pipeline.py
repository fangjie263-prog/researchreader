import unittest
from pathlib import Path
from typing import Any

from researchreader.researchreader.adapters import DocumentAdapter, TranslationAdapter
from researchreader.researchreader.pipeline import PipelineContext, PipelineResult, PipelineStatus
from researchreader.researchreader.pipeline.translation import TranslationPipeline


class TestTranslationPipeline(unittest.TestCase):
    def test_successful_execution_flow(self):
        adapter = _FakeTranslationDocumentAdapter()
        pipeline = TranslationPipeline(adapter_factory=_FakeAdapterFactory(adapter))
        context = _context()

        result = pipeline.execute(context)

        self.assertTrue(result.ok)
        self.assertEqual(adapter.calls, ["load", "translate", "save"])
        self.assertEqual(result.metadata["document_type"], "epub")

    def test_adapter_selection(self):
        factory = _FakeAdapterFactory(_FakeTranslationDocumentAdapter())
        pipeline = TranslationPipeline(adapter_factory=factory)

        pipeline.execute(_context(source_path=Path("book.epub")))

        self.assertEqual(factory.requested_path, Path("book.epub"))

    def test_invalid_input_returns_failed_result(self):
        pipeline = TranslationPipeline(adapter_factory=_FakeAdapterFactory(_FakeTranslationDocumentAdapter()))

        result = pipeline.execute(
            PipelineContext(
                task="translation",
                provider="openai",
                model="gpt-4o-mini",
                target_language="Chinese",
                output_path=Path("out.epub"),
            )
        )

        self.assertFalse(result.ok)
        self.assertIn("source_path is required", result.errors[0])

    def test_adapter_failure_returns_failed_result(self):
        pipeline = TranslationPipeline(adapter_factory=_FakeAdapterFactory(_FailingLoadAdapter()))

        result = pipeline.execute(_context())

        self.assertFalse(result.ok)
        self.assertIn("load failed", result.errors[0])

    def test_translation_failure_skips_save_and_preserves_result(self):
        adapter = _FailingTranslationAdapter()
        pipeline = TranslationPipeline(adapter_factory=_FakeAdapterFactory(adapter))

        result = pipeline.execute(_context())

        self.assertFalse(result.ok)
        self.assertEqual(adapter.calls, ["load", "translate"])
        self.assertIn("translation failed", result.errors)

    def test_result_metadata_and_timing(self):
        pipeline = TranslationPipeline(adapter_factory=_FakeAdapterFactory(_FakeTranslationDocumentAdapter()))

        result = pipeline.execute(_context())

        self.assertEqual(result.metadata["provider"], "openai")
        self.assertEqual(result.metadata["model"], "gpt-4o-mini")
        self.assertEqual(result.metadata["document_type"], "epub")
        self.assertIsNotNone(result.start_time)
        self.assertIsNotNone(result.end_time)
        self.assertIsNotNone(result.duration_seconds)
        assert result.duration_seconds is not None
        self.assertGreaterEqual(result.duration_seconds, 0)


def _context(source_path: Path = Path("book.epub")) -> PipelineContext:
    return PipelineContext(
        task="translation",
        provider="openai",
        model="gpt-4o-mini",
        target_language="Chinese",
        source_path=source_path,
        output_path=Path("translated.epub"),
    )


class _FakeAdapterFactory:
    def __init__(self, adapter: DocumentAdapter) -> None:
        self._adapter = adapter
        self.requested_path: Path | None = None

    def create_for_path(self, source_path: Path | str) -> DocumentAdapter:
        self.requested_path = Path(source_path)
        return self._adapter


class _FakeTranslationDocumentAdapter(DocumentAdapter, TranslationAdapter):
    document_type = "epub"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.last_context: PipelineContext | None = None

    def load(self, source_path: Path) -> dict[str, str]:
        self.calls.append("load")
        return {"source": str(source_path)}

    def save(self, document: Any, output_path: Path) -> None:
        self.calls.append("save")

    def detect(self, source_path: Path) -> bool:
        return True

    def metadata(self, document: Any) -> dict[str, Any]:
        return {}

    def translate(self, context: PipelineContext) -> PipelineResult:
        self.calls.append("translate")
        self.last_context = context
        return PipelineResult(status=PipelineStatus.SUCCESS, task=context.task)


class _FailingLoadAdapter(_FakeTranslationDocumentAdapter):
    def load(self, source_path: Path) -> dict[str, str]:
        raise ValueError("load failed")


class _FailingTranslationAdapter(_FakeTranslationDocumentAdapter):
    def translate(self, context: PipelineContext) -> PipelineResult:
        self.calls.append("translate")
        return PipelineResult(
            status=PipelineStatus.FAILED,
            task=context.task,
            errors=("translation failed",),
        )
