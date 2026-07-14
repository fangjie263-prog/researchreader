from __future__ import annotations

import argparse
from pathlib import Path

from ..provider_manager import ProviderManager, ProviderSummary
from ..providers import ProviderTestResult


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ResearchReader")
    parser.add_argument("--config", type=Path, default=None, help="Path to provider config TOML")
    command_group = parser.add_mutually_exclusive_group(required=True)
    command_group.add_argument("--models", action="store_true", help="List configured provider models")
    command_group.add_argument("--test", action="store_true", help="Test provider connectivity and latency")
    args = parser.parse_args(argv)

    manager = ProviderManager.from_config(args.config)
    if args.models:
        _print_models(manager.summaries())
        return 0
    if args.test:
        results = manager.test_all()
        _print_test_results(results)
        return 0 if all(result.ok for result in results) else 1
    return 1


def _print_models(summaries: list[ProviderSummary]) -> None:
    print("Models by provider:")
    for summary in summaries:
        status = "configured" if summary.configured else "configuration error"
        print(f"{summary.display_name} ({summary.name})")
        print(f"  kind: {summary.kind}")
        print(f"  base_url: {summary.base_url}")
        print(f"  configured_model: {summary.model}")
        print(f"  api_key_env: {summary.api_key_env}")
        print(f"  status: {status}")
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
