import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from researchreader.researchreader.config.resolver import ProviderResolver
from researchreader.researchreader.config.settings import Settings, load_settings
from researchreader.researchreader.pipeline import PipelineContext
from researchreader.researchreader.pipeline.translation import TranslationPipeline
from tests.test_researchreader_translation_pipeline import _FakeAdapterFactory, _FakeTranslationDocumentAdapter


class TestSettings(unittest.TestCase):
    def test_settings_loading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.toml"
            output_dir = Path(temp_dir) / "out"
            settings_path.write_text(
                f"""
default_provider = "openai"
default_model_override = "gpt-test"
target_language = "Spanish"
concurrency = 2
retry_count = 1
timeout = 30
output_directory = "{output_dir.as_posix()}"
enable_cache = false
log_level = "DEBUG"
""".strip(),
                encoding="utf-8",
            )

            settings = load_settings(settings_path)

        self.assertEqual(settings.default_provider, "openai")
        self.assertEqual(settings.default_model_override, "gpt-test")
        self.assertEqual(settings.target_language, "Spanish")
        self.assertEqual(settings.concurrency, 2)
        self.assertFalse(settings.enable_cache)

    def test_missing_settings_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(Path(temp_dir) / "missing.toml")

        self.assertEqual(settings.default_provider, "deepseek")
        self.assertEqual(settings.target_language, "Chinese")

    def test_invalid_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.toml"
            settings_path.write_text('default_provider = ""\nconcurrency = 0\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "concurrency"):
                load_settings(settings_path)

    def test_output_directory_creation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "created"
            settings_path = Path(temp_dir) / "settings.toml"
            settings_path.write_text(f'output_directory = "{output_dir.as_posix()}"\n', encoding="utf-8")

            load_settings(settings_path)

            self.assertTrue(output_dir.exists())


class TestProviderResolver(unittest.TestCase):
    def test_provider_resolution_and_environment_lookup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = _provider_catalog(temp_dir)
            settings = Settings(default_provider="openai", output_directory=Path(temp_dir) / "out")

            with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
                resolved = ProviderResolver(settings=settings, provider_catalog_path=catalog_dir).resolve()

        self.assertEqual(resolved.id, "openai")
        self.assertEqual(resolved.api_key, "env-key")
        self.assertEqual(resolved.base_url, "https://api.openai.com/v1")

    def test_configuration_priority_explicit_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = _provider_catalog(temp_dir)
            settings = Settings(default_provider="openai", output_directory=Path(temp_dir) / "out")

            resolved = ProviderResolver(settings=settings, provider_catalog_path=catalog_dir).resolve(provider="deepseek")

        self.assertEqual(resolved.id, "deepseek")

    def test_model_resolution_context_model_wins(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = _provider_catalog(temp_dir)
            settings = Settings(default_provider="openai", default_model_override="settings-model")

            resolved = ProviderResolver(settings=settings, provider_catalog_path=catalog_dir).resolve(model="context-model")

        self.assertEqual(resolved.model, "context-model")
        self.assertEqual(resolved.model_source, "PipelineContext")

    def test_model_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = _provider_catalog(temp_dir)
            settings = Settings(default_provider="openai", default_model_override="settings-model")

            resolved = ProviderResolver(settings=settings, provider_catalog_path=catalog_dir).resolve()

        self.assertEqual(resolved.model, "settings-model")
        self.assertEqual(resolved.model_source, "settings override")

    def test_provider_fallback_to_settings_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = _provider_catalog(temp_dir)
            settings = Settings(default_provider="deepseek")

            resolved = ProviderResolver(settings=settings, provider_catalog_path=catalog_dir).resolve()

        self.assertEqual(resolved.id, "deepseek")
        self.assertEqual(resolved.model, "deepseek-chat")
        self.assertEqual(resolved.model_source, "provider default")


class TestTranslationPipelineConfiguration(unittest.TestCase):
    def test_translation_pipeline_automatic_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = _provider_catalog(temp_dir)
            settings = Settings(
                default_provider="openai",
                target_language="Chinese",
                output_directory=Path(temp_dir) / "out",
            )
            resolver = ProviderResolver(settings=settings, provider_catalog_path=catalog_dir)
            adapter = _FakeTranslationDocumentAdapter()
            pipeline = TranslationPipeline(
                adapter_factory=_FakeAdapterFactory(adapter),
                provider_resolver=resolver,
                settings=settings,
            )

            result = pipeline.execute(
                PipelineContext(
                    source_path=Path("book.epub"),
                    output_path=Path(temp_dir) / "nested" / "translated.epub",
                )
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.metadata["provider"], "openai")
        self.assertEqual(result.metadata["model"], "gpt-4o-mini")
        self.assertEqual(adapter.last_context.target_language, "Chinese")
        self.assertEqual(adapter.last_context.resolved_provider.id, "openai")


def _provider_catalog(temp_dir: str) -> Path:
    catalog_dir = Path(temp_dir) / "providers"
    catalog_dir.mkdir()
    (catalog_dir / "openai.toml").write_text(
        """
id = "openai"
display_name = "OpenAI"
kind = "openai-compatible"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
default_model = "gpt-4o-mini"
enabled = true
""".strip(),
        encoding="utf-8",
    )
    (catalog_dir / "deepseek.toml").write_text(
        """
id = "deepseek"
display_name = "DeepSeek"
kind = "openai-compatible"
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"
default_model = "deepseek-chat"
enabled = true
""".strip(),
        encoding="utf-8",
    )
    return catalog_dir
