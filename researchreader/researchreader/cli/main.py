from __future__ import annotations

import argparse
from pathlib import Path

from ..config.resolver import ProviderResolver
from ..config.settings import Settings, load_settings
from ..pipeline import PipelineContext, PipelineResult
from ..pipeline.translation import TranslationPipeline
from ..provider_manager import ProviderManager, ProviderSummary
from ..providers import ProviderTestResult


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ResearchReader")
    parser.add_argument("--config", type=Path, default=None, help="Path to provider catalog directory or config TOML")
    subparsers = parser.add_subparsers(dest="command")
    translate_parser = subparsers.add_parser("translate", help="Translate a document through ResearchReader")
    translate_parser.add_argument("input_path", type=Path, help="Input document path")
    translate_parser.add_argument("output_path", type=Path, nargs="?", help="Optional output document path")

    command_group = parser.add_mutually_exclusive_group()
    command_group.add_argument("--models", action="store_true", help="List configured provider models")
    command_group.add_argument("--test", action="store_true", help="Test provider connectivity and latency")
    command_group.add_argument("--settings", action="store_true", help="Show resolved ResearchReader settings")
    args = parser.parse_args(argv)

    if args.command == "translate":
        return _run_translate(args.input_path, args.output_path)
    if args.settings:
        return _print_settings()

    try:
        manager = ProviderManager.from_config(args.config)
    except ValueError as error:
        print(f"Configuration error: {error}")
        return 1
    if args.models:
        _print_models(manager.summaries())
        return 0
    if args.test:
        results = manager.test_all()
        _print_test_results(results)
        return 0 if all(result.ok for result in results) else 1
    parser.print_help()
    return 1


def _run_translate(input_path: Path, output_path: Path | None) -> int:
    print("Loading configuration...")
    try:
        settings = load_settings()
        target_path = output_path or _default_translation_output(input_path, settings)
        context = PipelineContext(source_path=input_path, output_path=target_path)
        pipeline = TranslationPipeline(
            settings=settings,
            provider_resolver=ProviderResolver(settings=settings),
        )
    except ValueError as error:
        print(f"Configuration error: {error}")
        return 1

    print("Resolving provider...")
    print("Loading EPUB...")
    print("Starting translation...")
    print("Saving translated EPUB...")
    result = pipeline.execute(context)
    if not result.ok:
        print("Translation failed.")
        _print_pipeline_errors(result)
        return 1

    print("Done.")
    _print_translation_summary(result)
    return 0


def _default_translation_output(input_path: Path, settings: Settings) -> Path:
    source_path = Path(input_path)
    suffix = source_path.suffix or ".epub"
    return settings.output_directory / f"{source_path.stem}_translated{suffix}"


def _print_translation_summary(result: PipelineResult) -> None:
    metadata = result.metadata
    output_file = result.artifacts[0] if result.artifacts else ""
    print("")
    print("Translation completed successfully.")
    print(f"Provider: {metadata.get('provider', '')}")
    print(f"Model: {metadata.get('model', '')}")
    print(f"Target language: {metadata.get('target_language', '')}")
    print(f"Elapsed time: {_format_duration_seconds(result.duration_seconds)}")
    print(f"Output file: {output_file}")


def _print_pipeline_errors(result: PipelineResult) -> None:
    if not result.errors:
        print("Unknown error.")
        return
    for error in result.errors:
        print(f"Error: {error}")


def _print_settings() -> int:
    try:
        settings = load_settings()
        resolved_provider = ProviderResolver(settings=settings).resolve()
    except ValueError as error:
        print(f"Configuration error: {error}")
        return 1

    print("ResearchReader settings")
    print("=======================")
    print(f"Current provider: {resolved_provider.display_name} ({resolved_provider.id})")
    print(f"Resolved model: {resolved_provider.model} ({resolved_provider.model_source})")
    print(f"Target language: {settings.target_language}")
    print(f"Output directory: {settings.output_directory}")
    print(f"Concurrency: {settings.concurrency}")
    print(f"Retry count: {settings.retry_count}")
    print(f"Timeout: {settings.timeout}")
    print(f"Cache: {_format_yes_no(settings.enable_cache)}")
    print(f"Logging: {settings.log_level}")
    return 0


def _print_models(summaries: list[ProviderSummary]) -> None:
    print("Models by provider:")
    groups = (
        ("Official Providers", "official"),
        ("Gateway Providers", "gateway"),
        ("Custom Providers", "custom"),
    )
    for title, provider_type in groups:
        group = [summary for summary in summaries if summary.provider_type == provider_type]
        if not group:
            continue
        print("")
        print(title)
        print("-" * len(title))
        for summary in group:
            _print_provider_summary(summary)


def _print_provider_summary(summary: ProviderSummary) -> None:
    if not summary.enabled:
        status = "disabled"
    else:
        status = "configured" if summary.configured else "configuration error"
    print(f"{summary.display_name} ({summary.name})")
    print(f"  kind: {summary.kind}")
    print(f"  base_url: {summary.base_url}")
    print(f"  configured_model: {summary.model}")
    print(f"  api_key_env: {summary.api_key_env}")
    if summary.country:
        print(f"  country: {summary.country}")
    if summary.website:
        print(f"  website: {summary.website}")
    print(f"  status: {status}")
    if summary.description:
        print(f"  description: {summary.description}")
    for error in summary.configuration_errors:
        print(f"  error: {error}")
    print("  models:")
    if not summary.models:
        print("    none registered")
    for model in summary.models:
        selected = " (configured)" if model.name == summary.model else ""
        print(f"    - {model.name}{selected}")
        print(f"      context_length: {model.context_length}")
        print(
            "      capabilities: "
            f"stream={_format_yes_no(model.supports_stream)}, "
            f"vision={_format_yes_no(model.supports_image)}, "
            f"reasoning={_format_yes_no(model.supports_reasoning)}, "
            f"embeddings={_format_yes_no(model.supports_embedding)}, "
            f"tools={_format_yes_no(model.supports_tool_call)}"
        )


def _print_test_results(results: list[ProviderTestResult]) -> None:
    passed = sum(1 for result in results if result.ok)
    failed = len(results) - passed
    print("Provider diagnostics")
    print("====================")
    print(f"Health: {passed} passed, {failed} failed, {len(results)} total")
    print("")
    for result in results:
        capabilities = result.capabilities
        status = "PASS" if result.ok else "FAIL"
        print(f"Provider: {result.display_name} ({result.provider_name})")
        print(f"Status: {status}")
        print(f"Model: {result.model}")
        print(f"Configuration: {_format_pass_fail(result.configuration_ok)}")
        print(f"API Connectivity: {_format_pass_fail(result.connectivity_ok)}")
        print(f"Model Availability: {_format_pass_fail(result.model_available)}")
        print(f"First Token: {_format_duration(result.first_token_latency_ms)}")
        print(f"Total Time: {_format_duration(result.total_response_time_ms)}")
        print("Capabilities:")
        print(f"  Streaming: {_format_yes_no(capabilities.supports_stream)}")
        print(f"  Vision: {_format_yes_no(capabilities.supports_image)}")
        print(f"  Embeddings: {_format_yes_no(capabilities.supports_embedding)}")
        print(f"  Reasoning: {_format_yes_no(capabilities.supports_reasoning)}")
        print(f"  Tool Calling: {_format_yes_no(capabilities.supports_tool_call)}")
        print(f"  Cache: {_format_yes_no(capabilities.supports_cache)}")
        for error in result.errors:
            print(f"Error: {error}")
        print("")


def _format_pass_fail(value: bool) -> str:
    return "PASS" if value else "FAIL"


def _format_yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _format_duration(value_ms: float | None) -> str:
    if value_ms is None:
        return "n/a"
    return f"{value_ms / 1000:.1f}s"


def _format_duration_seconds(value_seconds: float | None) -> str:
    if value_seconds is None:
        return "n/a"
    return f"{value_seconds:.1f}s"
