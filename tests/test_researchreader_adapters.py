import tempfile
import unittest
from enum import Enum
from pathlib import Path
from typing import Any
from unittest.mock import patch

from researchreader.researchreader.adapters import (
    AdapterFactory,
    AdapterRegistry,
    DocumentAdapter,
    EPUBAdapter,
    EPUBDocument,
    TranslationAdapter,
)
from researchreader.researchreader.pipeline import PipelineContext, PipelineResult, PipelineStatus


class TestAdapterRegistry(unittest.TestCase):
    def test_adapter_registration_and_lookup(self):
        registry = AdapterRegistry(include_defaults=False)

        registry.register_adapter("epub", _FakeDocumentAdapter)

        self.assertIs(registry.get_adapter("epub"), _FakeDocumentAdapter)
        self.assertEqual(registry.list_adapters(), ("epub",))

    def test_duplicate_adapter_detection(self):
        registry = AdapterRegistry(include_defaults=False)
        registry.register_adapter("epub", _FakeDocumentAdapter)

        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register_adapter("epub", _OtherFakeDocumentAdapter)

    def test_unknown_adapter_lookup(self):
        registry = AdapterRegistry(include_defaults=False)

        with self.assertRaises(KeyError):
            registry.get_adapter("pdf")

    def test_adapter_must_inherit_document_adapter(self):
        registry = AdapterRegistry(include_defaults=False)

        with self.assertRaises(TypeError):
            registry.register_adapter("epub", object)  # type: ignore[arg-type]


class TestAdapterFactory(unittest.TestCase):
    def test_factory_creation_by_file_type(self):
        registry = AdapterRegistry(include_defaults=False)
        registry.register_adapter("epub", _FakeDocumentAdapter)
        factory = AdapterFactory(registry)

        adapter = factory.create_for_path("book.epub")

        self.assertIsInstance(adapter, _FakeDocumentAdapter)

    def test_factory_normalizes_markdown_extension(self):
        registry = AdapterRegistry(include_defaults=False)
        registry.register_adapter("markdown", _FakeDocumentAdapter)
        factory = AdapterFactory(registry)

        adapter = factory.create_for_path(Path("notes.md"))

        self.assertIsInstance(adapter, _FakeDocumentAdapter)

    def test_factory_creates_default_epub_adapter(self):
        factory = AdapterFactory()

        adapter = factory.create_for_path("book.epub")

        self.assertIsInstance(adapter, EPUBAdapter)


class TestAdapterInterfaces(unittest.TestCase):
    def test_document_adapter_inheritance(self):
        adapter = _FakeDocumentAdapter()

        self.assertIsInstance(adapter, DocumentAdapter)
        self.assertTrue(adapter.detect(Path("book.epub")))
        self.assertEqual(adapter.metadata({}), {"title": "fake"})

    def test_translation_adapter_inheritance(self):
        adapter = _FakeTranslationAdapter()
        context = PipelineContext(task="translation", provider="openai", model="gpt-4o-mini")

        result = adapter.translate(context)

        self.assertIsInstance(adapter, TranslationAdapter)
        self.assertTrue(result.ok)
        self.assertEqual(result.task, "translation")


class TestEPUBAdapter(unittest.TestCase):
    def test_epub_adapter_is_registered_by_default(self):
        registry = AdapterRegistry()

        self.assertIs(registry.get_adapter("epub"), EPUBAdapter)

    def test_successful_adapter_initialization(self):
        adapter = EPUBAdapter()

        self.assertEqual(adapter.document_type, "epub")
        self.assertTrue(adapter.detect(Path("book.epub")))

    def test_load_rejects_invalid_extension(self):
        adapter = EPUBAdapter()

        with self.assertRaisesRegex(ValueError, "expected an .epub file"):
            adapter.load(Path("book.pdf"))

    def test_load_rejects_missing_file(self):
        adapter = EPUBAdapter()

        with self.assertRaisesRegex(FileNotFoundError, "does not exist"):
            adapter.load(Path("missing.epub"))

    def test_load_returns_epub_document(self):
        adapter = EPUBAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "book.epub"
            source_path.write_bytes(b"fake epub")

            document = adapter.load(source_path)

        self.assertIsInstance(document, EPUBDocument)
        self.assertEqual(document.source_path.name, "book.epub")

    def test_translate_returns_failed_result_for_invalid_context(self):
        adapter = EPUBAdapter()
        context = PipelineContext(task="translation", provider="openai", model="gpt-4o-mini")

        result = adapter.translate(context)

        self.assertFalse(result.ok)
        self.assertIn("source_path is required", result.errors[0])

    def test_translate_uses_epub_translator_backend(self):
        adapter = EPUBAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "book.epub"
            output_path = Path(temp_dir) / "translated.epub"
            source_path.write_bytes(b"fake epub")
            context = PipelineContext(
                task="translation",
                provider="openai",
                model="gpt-4o-mini",
                target_language="Chinese",
                source_path=source_path,
                output_path=output_path,
                runtime_options={
                    "api_key": "test-key",
                    "base_url": "https://api.openai.com/v1",
                },
            )

            backend = _FakeEPUBBackend()
            with patch("researchreader.researchreader.adapters.epub._load_epub_backend", return_value=backend):
                result = adapter.translate(context)

        self.assertTrue(result.ok)
        self.assertEqual(result.artifacts, (output_path,))
        self.assertEqual(backend.llm_calls, 1)
        self.assertEqual(backend.translate_calls, 1)


class _FakeDocumentAdapter(DocumentAdapter):
    document_type = "epub"

    def load(self, source_path: Path) -> dict[str, str]:
        return {"source": str(source_path)}

    def save(self, document: Any, output_path: Path) -> None:
        return None

    def detect(self, source_path: Path) -> bool:
        return source_path.suffix == ".epub"

    def metadata(self, document: Any) -> dict[str, Any]:
        return {"title": "fake"}


class _OtherFakeDocumentAdapter(_FakeDocumentAdapter):
    pass


class _FakeTranslationAdapter(TranslationAdapter):
    document_type = "epub"

    def translate(self, context: PipelineContext) -> PipelineResult:
        return PipelineResult(status=PipelineStatus.SUCCESS, task=context.task)


class _FakeSubmitKind(Enum):
    APPEND_BLOCK = 1


class _FakeEPUBBackend:
    SubmitKind = _FakeSubmitKind

    def __init__(self) -> None:
        self.llm_calls = 0
        self.translate_calls = 0

    def LLM(self, **kwargs):
        self.llm_calls += 1
        return {"llm": kwargs}

    def translate(self, **kwargs):
        self.translate_calls += 1
