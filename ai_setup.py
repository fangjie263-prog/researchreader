"""Interactive AI provider setup and resilient model benchmarking."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

from ai_config import AIServiceConfig
from ai_service import AIService, AIServiceError


ROOT = Path(__file__).resolve().parent
BENCHMARK_PATH = ROOT / "benchmark.json"


class UnknownProviderError(RuntimeError):
    pass


def setup(visible_key: bool = False) -> Path:
    current = AIServiceConfig.from_env()
    base_url = input(f"Base URL [{current.base_url}]: ").strip() or current.base_url
    if visible_key:
        api_key = input("API key (paste; visible on screen): ").strip() or current.api_key
    else:
        api_key = getpass.getpass("API key (paste, input stays hidden; leave blank to keep current): ").strip() or current.api_key
    model = input(f"Model (leave blank for automatic recommendation) [{current.model}]: ").strip() or current.model
    config = AIServiceConfig(True, api_key, base_url, model, current.endpoint)
    path = config.save()
    print(f"Saved settings to {path}")
    return path


def _provider_name(config: AIServiceConfig, provider: str) -> str:
    if provider:
        return provider
    return config.base_url.rstrip("/").split("/")[-2] if "/" in config.base_url else config.base_url


def _select_models(ids: list[str], provider: str, model: str, top: int, endpoint: str = "") -> list[str]:
    if model:
        return [item for item in ids if item.casefold() == model.casefold()] or [model]
    if provider:
        if provider.casefold() not in endpoint.casefold():
            matching = [item for item in ids if provider.casefold() in item.casefold()]
            if not matching:
                raise UnknownProviderError(provider)
            ids = matching
    return ids[:top]


def run_benchmark(timeout: int = 30, top: int = 10, provider: str = "", model: str = "") -> tuple[dict, int]:
    config = AIServiceConfig.from_env()
    if not config.is_active:
        raise RuntimeError("AI is not configured. Run: python ai_setup.py setup")
    service = AIService(config)
    try:
        models = service.list_models()
        ids = [item["id"] for item in models]
    except AIServiceError as exc:
        if not model and not config.model:
            raise RuntimeError(f"Cannot list models: {exc}") from exc
        ids = [model or config.model]
        print(f"/models unavailable ({exc}); testing the configured model instead.")

    selected = _select_models(ids, provider, model, max(1, top), config.base_url)
    provider_label = _provider_name(config, provider).upper()
    print(f"Provider:\n{provider_label}\n\nTesting:\n{len(selected)} model(s)\n\nTimeout:\n{timeout} s")
    results = [service.benchmark_model(item, timeout=timeout) for item in selected]
    results.sort(key=lambda item: (item["status"] != "PASS", item["latency"] is None, item["latency"] or float("inf")))

    report = {
        "provider": provider_label,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "timeout_seconds": timeout,
        "models": results,
    }
    path = Path(os.environ.get("AI_BENCHMARK_PATH", BENCHMARK_PATH))
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for item in results:
        latency = f"{item['latency']:.2f} s" if item["latency"] is not None else "-"
        print(f"{item['model']}\n{item['status']}\n{latency}")
        if item.get("error"):
            print(f"Error: {item['error']}")
        print()

    passed = sum(item["status"] == "PASS" for item in results)
    failed = len(results) - passed
    print("Summary\n\nPASS:\n{}\n\nFAILED:\n{}".format(passed, failed))
    print(f"Saved benchmark: {path}")
    if passed:
        print(f"Fastest model: {next(item['model'] for item in results if item['status'] == 'PASS')}")
    return report, 0 if passed else 1


def test_provider(timeout: int = 30, top: int = 10, provider: str = "", model: str = "") -> int:
    try:
        _, code = run_benchmark(timeout, top, provider, model)
        return code
    except (AIServiceError, RuntimeError, ValueError, OSError, socket.timeout, TimeoutError) as exc:
        if isinstance(exc, UnknownProviderError):
            print(f"Unknown provider: {exc}")
            return 1
        print(f"Provider benchmark setup failed: {exc}")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure and benchmark an OpenAI-compatible provider")
    parser.add_argument("command", choices=("setup", "test"), nargs="?", default="setup")
    parser.add_argument("--visible-key", action="store_true", help="show the key while pasting it")
    parser.add_argument("--timeout", type=int, default=30, help="per-model timeout in seconds")
    parser.add_argument("--top", type=int, default=10, help="maximum number of models to test")
    parser.add_argument("--provider", default="", help="provider label or model-id filter")
    parser.add_argument("--model", default="", help="test exactly one model")
    args = parser.parse_args()
    if args.command == "setup":
        setup(args.visible_key)
        return
    raise SystemExit(test_provider(args.timeout, args.top, args.provider, args.model))


if __name__ == "__main__":
    main()
