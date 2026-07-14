import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from researchreader.researchreader.cli.main import main
from researchreader.researchreader.config import ProviderConfig, load_provider_catalog, load_provider_configs
from researchreader.researchreader.models import ModelInfo, ModelRegistry, load_model_registry
from researchreader.researchreader.provider_manager import ProviderManager
from researchreader.researchreader.providers import (
    OpenAICompatibleProvider,
    ProviderCapabilities,
    ProviderFactory,
    ProviderRegistry,
)


class TestProviderConfig(unittest.TestCase):
    def test_load_provider_configs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[providers.openai]
display_name = "OpenAI"
kind = "openai-compatible"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model = "gpt-test"
""".strip(),
                encoding="utf-8",
            )

            configs = load_provider_configs(config_path)

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].name, "openai")
        self.assertEqual(configs[0].model, "gpt-test")

    def test_load_provider_configs_from_array_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[[providers]]
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

            configs = load_provider_configs(config_path)

        self.assertEqual(len(configs), 1)
        self.assertEqual(configs[0].name, "deepseek")
        self.assertEqual(configs[0].model, "deepseek-chat")

    def test_custom_provider_loading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[[providers]]
id = "my-company"
display_name = "My Company LLM"
kind = "openai-compatible"
base_url = "https://llm.example.com/v1"
api_key_env = "MY_COMPANY_API_KEY"
default_model = "company-chat"
enabled = true
""".strip(),
                encoding="utf-8",
            )

            configs = load_provider_configs(config_path)

        self.assertEqual(configs[0].name, "my-company")
        self.assertEqual(configs[0].display_name, "My Company LLM")

    def test_provider_catalog_directory_scanning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = Path(temp_dir)
            (catalog_dir / "one.toml").write_text(
                """
id = "one"
display_name = "One"
kind = "openai-compatible"
base_url = "https://one.example.com/v1"
api_key_env = "ONE_API_KEY"
default_model = "one-chat"
enabled = true
""".strip(),
                encoding="utf-8",
            )
            (catalog_dir / "two.toml").write_text(
                """
id = "two"
display_name = "Two"
kind = "openai-compatible"
base_url = "https://two.example.com/v1"
api_key_env = "TWO_API_KEY"
default_model = "two-chat"
enabled = true
""".strip(),
                encoding="utf-8",
            )

            configs = load_provider_catalog(catalog_dir)

        self.assertEqual([config.name for config in configs], ["one", "two"])

    def test_provider_metadata_loading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = Path(temp_dir)
            (catalog_dir / "gateway.toml").write_text(
                """
id = "gateway"
display_name = "Gateway"
description = "Private gateway"
provider_type = "gateway"
country = "Custom"
website = "https://gateway.example.com"
kind = "openai-compatible"
base_url = "https://gateway.example.com/v1"
api_key_env = "GATEWAY_API_KEY"
default_model = "auto"
enabled = false
""".strip(),
                encoding="utf-8",
            )

            config = load_provider_catalog(catalog_dir)[0]

        self.assertEqual(config.provider_type, "gateway")
        self.assertEqual(config.description, "Private gateway")
        self.assertEqual(config.country, "Custom")
        self.assertEqual(config.website, "https://gateway.example.com")

    def test_duplicate_provider_detection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = Path(temp_dir)
            (catalog_dir / "one.toml").write_text(
                """
id = "duplicate"
display_name = "One"
kind = "openai-compatible"
base_url = "https://one.example.com/v1"
api_key_env = "ONE_API_KEY"
default_model = "one-chat"
enabled = true
""".strip(),
                encoding="utf-8",
            )
            (catalog_dir / "two.toml").write_text(
                """
id = "duplicate"
display_name = "Two"
kind = "openai-compatible"
base_url = "https://two.example.com/v1"
api_key_env = "TWO_API_KEY"
default_model = "two-chat"
enabled = true
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicated provider id"):
                load_provider_catalog(catalog_dir)

    def test_invalid_provider_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[[providers]]
id = "broken"
display_name = "Broken"
kind = "unsupported-kind"
base_url = ""
api_key_env = "BROKEN_API_KEY"
default_model = ""
enabled = true
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unsupported provider kind"):
                load_provider_configs(config_path)

    def test_disabled_provider_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[[providers]]
id = "disabled"
display_name = "Disabled"
kind = "openai-compatible"
base_url = "https://disabled.example.com/v1"
api_key_env = "DISABLED_API_KEY"
default_model = "disabled-chat"
enabled = false
""".strip(),
                encoding="utf-8",
            )

            configs = load_provider_configs(config_path)

        self.assertEqual(configs, [])

    def test_disabled_provider_is_present_in_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = Path(temp_dir)
            (catalog_dir / "disabled.toml").write_text(
                """
id = "disabled"
display_name = "Disabled"
kind = "openai-compatible"
base_url = "https://disabled.example.com/v1"
api_key_env = "DISABLED_API_KEY"
default_model = "disabled-chat"
enabled = false
""".strip(),
                encoding="utf-8",
            )

            configs = load_provider_catalog(catalog_dir)

        self.assertEqual(len(configs), 1)
        self.assertFalse(configs[0].enabled)

    def test_validation_reports_missing_api_key(self):
        config = ProviderConfig(
            name="openai",
            display_name="OpenAI",
            kind="openai-compatible",
            base_url="https://api.openai.com/v1",
            model="gpt-test",
            api_key_env="MISSING_RESEARCHREADER_TEST_KEY",
        )

        self.assertIn("missing API key environment variable", config.validate()[0])


class TestProviderManager(unittest.TestCase):
    def test_summaries_include_configuration_errors(self):
        manager = ProviderManager(
            [
                ProviderConfig(
                    name="openai",
                    display_name="OpenAI",
                    kind="openai-compatible",
                    base_url="",
                    model="",
                    api_key_env="MISSING_RESEARCHREADER_TEST_KEY",
                )
            ]
        )

        summary = manager.summaries()[0]

        self.assertFalse(summary.configured)
        self.assertIn("missing base_url", summary.configuration_errors)
        self.assertIn("missing model", summary.configuration_errors)

    def test_unregistered_custom_model_is_not_a_configuration_error(self):
        manager = ProviderManager(
            [
                ProviderConfig(
                    name="my-company",
                    display_name="My Company LLM",
                    kind="openai-compatible",
                    base_url="https://llm.example.com/v1",
                    model="company-chat",
                    api_key_env="MY_COMPANY_API_KEY",
                    api_key="test-key",
                )
            ]
        )

        summary = manager.summaries()[0]

        self.assertTrue(summary.configured)
        self.assertEqual(summary.configuration_errors, ())


class TestModelRegistry(unittest.TestCase):
    def test_model_lookup(self):
        registry = _model_registry()

        model = registry.get_model("test-model")

        self.assertEqual(model.provider, "openai")
        self.assertEqual(model.context_length, 123)

    def test_provider_grouping(self):
        registry = _model_registry()

        models = registry.list_models_by_provider("openai")

        self.assertEqual([model.name for model in models], ["test-model"])

    def test_invalid_model_lookup(self):
        registry = _model_registry()

        with self.assertRaises(KeyError):
            registry.get_model("missing-model")

    def test_registry_loading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_path = Path(temp_dir) / "models.toml"
            registry_path.write_text(
                """
[models."loaded-model"]
provider = "openai"
context_length = 456
supports_stream = true
supports_image = false
supports_reasoning = true
supports_embedding = false
supports_tool_call = true
""".strip(),
                encoding="utf-8",
            )

            registry = load_model_registry(registry_path)

        model = registry.get_model("loaded-model")
        self.assertEqual(model.provider, "openai")
        self.assertTrue(model.supports_stream)
        self.assertTrue(model.supports_tool_call)


class TestProviderFactory(unittest.TestCase):
    def test_factory_uses_registered_provider(self):
        registry = ProviderRegistry()
        registry.register("custom", _FakeProvider)
        factory = ProviderFactory(registry)

        provider = factory.create(
            ProviderConfig(
                name="custom",
                display_name="Custom",
                kind="custom",
                base_url="https://example.com",
                model="custom-model",
                api_key_env="CUSTOM_API_KEY",
                api_key="test-key",
            )
        )

        self.assertIsInstance(provider, _FakeProvider)


class TestOpenAICompatibleProvider(unittest.TestCase):
    def test_model_listing_parses_ids(self):
        provider = OpenAICompatibleProvider(_configured_provider())

        with patch("urllib.request.urlopen", return_value=_FakeResponse(b'{"data":[{"id":"m1"},{"id":"m2"}]}')):
            self.assertEqual(provider.list_models(), ["m1", "m2"])

    def test_first_token_latency_reads_stream(self):
        provider = OpenAICompatibleProvider(_configured_provider())
        stream = b'data: {"choices":[{"delta":{"content":"o"}}]}\n\ndata: [DONE]\n\n'

        with patch("urllib.request.urlopen", return_value=_FakeResponse(stream)):
            latency = provider.measure_first_token_latency()

        self.assertGreaterEqual(latency, 0)

    def test_provider_test_checks_model_availability_and_latency(self):
        provider = OpenAICompatibleProvider(_configured_provider())

        with (
            patch.object(provider, "list_models", side_effect=AssertionError("Models API should not be required")),
            patch.object(
                provider,
                "_measure_response_timings",
                return_value=_FakeTimings(first_token_latency_ms=12.5, total_response_time_ms=25.0),
            ),
        ):
            result = provider.test()

        self.assertTrue(result.ok)
        self.assertTrue(result.configuration_ok)
        self.assertTrue(result.connectivity_ok)
        self.assertTrue(result.model_available)
        self.assertEqual(result.first_token_latency_ms, 12.5)
        self.assertEqual(result.total_response_time_ms, 25.0)

    def test_completion_success_marks_model_available_when_models_api_is_unreliable(self):
        provider = OpenAICompatibleProvider(
            ProviderConfig(
                name="deepseek",
                display_name="DeepSeek",
                kind="openai-compatible",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat",
                api_key_env="DEEPSEEK_API_KEY",
                api_key="test-key",
            )
        )

        with (
            patch.object(provider, "list_models", side_effect=AssertionError("Models API should not be required")),
            patch.object(
                provider,
                "_measure_response_timings",
                return_value=_FakeTimings(first_token_latency_ms=100.0, total_response_time_ms=200.0),
            ),
        ):
            result = provider.test()

        self.assertTrue(result.ok)
        self.assertTrue(result.connectivity_ok)
        self.assertTrue(result.model_available)
        self.assertEqual(result.errors, ())

    def test_model_capabilities_are_exposed_by_registry(self):
        registry = _model_registry()

        capabilities = registry.get_model("test-model").to_capabilities()

        self.assertTrue(capabilities.supports_stream)
        self.assertTrue(capabilities.supports_image)
        self.assertTrue(capabilities.supports_tool_call)


class TestCli(unittest.TestCase):
    def test_models_command_prints_configured_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[providers.openai]
display_name = "OpenAI"
kind = "openai-compatible"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model = "gpt-4o-mini"
api_key = "test-key"
""".strip(),
                encoding="utf-8",
            )
            output = io.StringIO()
            with patch("sys.stdout", output):
                exit_code = main(["--config", str(config_path), "--models"])

        self.assertEqual(exit_code, 0)
        self.assertIn("OpenAI", output.getvalue())
        self.assertIn("gpt-4o-mini", output.getvalue())
        self.assertIn("Models by provider", output.getvalue())

    def test_models_command_includes_custom_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[[providers]]
id = "my-company"
display_name = "My Company LLM"
kind = "openai-compatible"
base_url = "https://llm.example.com/v1"
api_key_env = "MY_COMPANY_API_KEY"
default_model = "company-chat"
api_key = "test-key"
enabled = true
""".strip(),
                encoding="utf-8",
            )
            output = io.StringIO()
            with patch("sys.stdout", output):
                exit_code = main(["--config", str(config_path), "--models"])

        printed = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("My Company LLM", printed)
        self.assertIn("company-chat", printed)

    def test_models_command_groups_gateway_and_disabled_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = Path(temp_dir)
            (catalog_dir / "gateway.toml").write_text(
                """
id = "gateway"
display_name = "Gateway"
provider_type = "gateway"
kind = "openai-compatible"
base_url = "https://gateway.example.com/v1"
api_key_env = "GATEWAY_API_KEY"
default_model = "auto"
enabled = false
""".strip(),
                encoding="utf-8",
            )
            output = io.StringIO()
            with patch("sys.stdout", output):
                exit_code = main(["--config", str(catalog_dir), "--models"])

        printed = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Gateway Providers", printed)
        self.assertIn("Gateway", printed)
        self.assertIn("status: disabled", printed)

    def test_test_command_skips_disabled_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            catalog_dir = Path(temp_dir)
            (catalog_dir / "disabled.toml").write_text(
                """
id = "disabled"
display_name = "Disabled"
kind = "openai-compatible"
base_url = "https://disabled.example.com/v1"
api_key_env = "DISABLED_API_KEY"
default_model = "disabled-chat"
enabled = false
""".strip(),
                encoding="utf-8",
            )
            output = io.StringIO()
            with patch("sys.stdout", output):
                exit_code = main(["--config", str(catalog_dir), "--test"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Health: 0 passed, 0 failed, 0 total", output.getvalue())

    def test_test_command_prints_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[providers.openai]
display_name = "OpenAI"
kind = "openai-compatible"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
model = "gpt-4o-mini"
api_key = "test-key"
""".strip(),
                encoding="utf-8",
            )
            output = io.StringIO()
            with (
                patch("sys.stdout", output),
                patch.object(OpenAICompatibleProvider, "list_models", return_value=["gpt-4o-mini"]),
                patch.object(
                    OpenAICompatibleProvider,
                    "_measure_response_timings",
                    return_value=_FakeTimings(first_token_latency_ms=3800.0, total_response_time_ms=4600.0),
                ),
            ):
                exit_code = main(["--config", str(config_path), "--test"])

        printed = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Provider diagnostics", printed)
        self.assertIn("Status: PASS", printed)
        self.assertIn("First Token: 3.8s", printed)
        self.assertIn("Total Time: 4.6s", printed)
        self.assertIn("Streaming: Yes", printed)

    def test_test_command_uses_custom_openai_compatible_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[[providers]]
id = "my-company"
display_name = "My Company LLM"
kind = "openai-compatible"
base_url = "https://llm.example.com/v1"
api_key_env = "MY_COMPANY_API_KEY"
default_model = "company-chat"
api_key = "test-key"
enabled = true
""".strip(),
                encoding="utf-8",
            )
            output = io.StringIO()
            with (
                patch("sys.stdout", output),
                patch.object(
                    OpenAICompatibleProvider,
                    "_measure_response_timings",
                    return_value=_FakeTimings(first_token_latency_ms=100.0, total_response_time_ms=200.0),
                ),
            ):
                exit_code = main(["--config", str(config_path), "--test"])

        printed = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("My Company LLM", printed)
        self.assertIn("Status: PASS", printed)

    def test_cli_reports_invalid_configuration_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.toml"
            config_path.write_text(
                """
[[providers]]
id = "broken"
display_name = "Broken"
kind = "unsupported-kind"
base_url = "https://broken.example.com/v1"
api_key_env = "BROKEN_API_KEY"
default_model = "broken-chat"
enabled = true
""".strip(),
                encoding="utf-8",
            )
            output = io.StringIO()
            with patch("sys.stdout", output):
                exit_code = main(["--config", str(config_path), "--models"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Configuration error:", output.getvalue())


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def read(self) -> bytes:
        return self._body.read()

    def readline(self) -> bytes:
        return self._body.readline()


class _FakeTimings:
    def __init__(self, first_token_latency_ms: float, total_response_time_ms: float) -> None:
        self.first_token_latency_ms = first_token_latency_ms
        self.total_response_time_ms = total_response_time_ms


def _configured_provider() -> ProviderConfig:
    return ProviderConfig(
        name="openai",
        display_name="OpenAI",
        kind="openai-compatible",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key_env="RESEARCHREADER_TEST_API_KEY",
        api_key=os.environ.get("RESEARCHREADER_TEST_API_KEY", "test-key"),
    )


def _model_registry() -> ModelRegistry:
    return ModelRegistry(
        [
            ModelInfo(
                name="test-model",
                provider="openai",
                context_length=123,
                supports_stream=True,
                supports_image=True,
                supports_reasoning=True,
                supports_embedding=False,
                supports_tool_call=True,
            ),
            ModelInfo(
                name="other-model",
                provider="deepseek",
                context_length=456,
                supports_stream=True,
                supports_image=False,
                supports_reasoning=False,
                supports_embedding=False,
                supports_tool_call=False,
            ),
        ]
    )


class _FakeProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def list_models(self) -> list[str]:
        return []

    def measure_first_token_latency(self) -> float:
        return 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def test(self):
        raise NotImplementedError
