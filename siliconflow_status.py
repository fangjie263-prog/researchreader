"""Query SiliconFlow International API models and account balance."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.siliconflow.com/v1"
PRICING_AS_OF = "2026-07-24"

# Reference prices from SiliconFlow's current public pricing page, in USD per
# million input/output tokens. Prices can change; --recommend labels them as
# reference values and the live /models response remains the source of truth
# for availability.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "deepseek-ai/DeepSeek-V4-Flash": (0.13, 0.28),
    "deepseek-ai/DeepSeek-V3.2": (0.27, 0.42),
    "Qwen/Qwen3-30B-A3B-Instruct-2507": (0.09, 0.45),
    "Qwen/Qwen3-Coder-30B-A3B-Instruct": (0.07, 0.28),
    "Qwen/Qwen3-Coder-480B-A35B-Instruct": (0.25, 1.00),
}

TRANSLATION_RECOMMENDATIONS = (
    "deepseek-ai/DeepSeek-V4-Flash",
    "deepseek-ai/DeepSeek-V3.2",
    "Qwen/Qwen3-30B-A3B-Instruct-2507",
)
CODING_RECOMMENDATIONS = (
    "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    "deepseek-ai/DeepSeek-V3.2",
    "Qwen/Qwen3-Coder-480B-A35B-Instruct",
)


class SiliconFlowAPIError(RuntimeError):
    """Raised when SiliconFlow returns an error or cannot be reached."""


def _get_json(
    base_url: str,
    path: str,
    api_key: str,
    timeout: float,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urlencode(params)}"

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except OSError:
            detail = str(exc)
        raise SiliconFlowAPIError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise SiliconFlowAPIError(f"Network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise SiliconFlowAPIError("SiliconFlow returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise SiliconFlowAPIError("SiliconFlow returned an unexpected response")
    return payload


def fetch_models(
    base_url: str,
    api_key: str,
    timeout: float,
    model_type: str | None = None,
    sub_type: str | None = None,
) -> list[dict[str, Any]]:
    params = {
        key: value
        for key, value in (("type", model_type), ("sub_type", sub_type))
        if value
    }
    payload = _get_json(base_url, "/models", api_key, timeout, params)
    models = payload.get("data", [])
    if not isinstance(models, list):
        raise SiliconFlowAPIError("The models response does not contain a data list")
    return [model for model in models if isinstance(model, dict)]


def fetch_user_info(base_url: str, api_key: str, timeout: float) -> dict[str, Any]:
    payload = _get_json(base_url, "/user/info", api_key, timeout)
    info = payload.get("data", {})
    if not isinstance(info, dict):
        raise SiliconFlowAPIError("The user info response does not contain a data object")
    return info


def _post_json(
    base_url: str,
    path: str,
    api_key: str,
    body: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SiliconFlowAPIError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise SiliconFlowAPIError(f"Network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise SiliconFlowAPIError("SiliconFlow returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise SiliconFlowAPIError("SiliconFlow returned an unexpected response")
    return payload


def benchmark_model(
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
    task: str = "translation",
    max_tokens: int = 80,
) -> dict[str, Any]:
    """Send a small request and measure end-to-end latency and output speed."""
    prompts = {
        "translation": "Translate to natural Traditional Chinese: SiliconFlow provides fast and affordable model APIs.",
        "coding": "Write a Python function that returns the first repeated item in a list. Include a short explanation.",
        "short": "Reply with exactly: benchmark ok",
    }
    if task not in prompts:
        raise ValueError(f"Unknown benchmark task: {task}")

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompts[task]}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    started = time.perf_counter()
    payload = _post_json(base_url, "/chat/completions", api_key, body, timeout)
    elapsed = time.perf_counter() - started

    usage = payload.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
    try:
        output_tokens = int(output_tokens)
    except (TypeError, ValueError):
        output_tokens = 0
    content = ""
    choices = payload.get("choices", [])
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message", {})
        if isinstance(message, dict):
            content = str(message.get("content", ""))

    return {
        "model": model,
        "seconds": round(elapsed, 3),
        "output_tokens": output_tokens,
        "tokens_per_second": round(output_tokens / elapsed, 2) if elapsed else None,
        "input_tokens": usage.get("prompt_tokens", usage.get("input_tokens")),
        "price": MODEL_PRICING.get(model),
        "preview": content.replace("\n", " ")[:160],
    }


def recommendation_report(available_models: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    available = {str(model.get("id")) for model in (available_models or [])}

    def make_rows(model_ids: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = []
        for rank, model in enumerate(model_ids, start=1):
            input_price, output_price = MODEL_PRICING[model]
            rows.append({
                "rank": rank,
                "model": model,
                "input_usd_per_million": input_price,
                "output_usd_per_million": output_price,
                "available": model in available if available_models is not None else None,
            })
        return rows

    return {
        "translation": make_rows(TRANSLATION_RECOMMENDATIONS),
        "coding": make_rows(CODING_RECOMMENDATIONS),
    }


def _print_recommendations(report: dict[str, list[dict[str, Any]]]) -> None:
    print(f"Recommendations (reference pricing as of {PRICING_AS_OF}, USD/M tokens)")
    for category, rows in report.items():
        print(f"\n{category.title()}:")
        for row in rows:
            availability = "available" if row["available"] else "check availability"
            print(
                f"{row['rank']}. {row['model']} | "
                f"input ${row['input_usd_per_million']:.2f} / output ${row['output_usd_per_million']:.2f} | {availability}"
            )


def _print_benchmarks(results: list[dict[str, Any]]) -> None:
    print("\nBenchmark results (one short request per model; lower seconds / higher tok/s is faster):")
    for result in results:
        if "error" in result:
            print(f"- {result['model']}: ERROR - {result['error']}")
            continue
        speed = result["tokens_per_second"]
        speed_text = f"{speed} tok/s" if speed is not None else "n/a tok/s"
        print(f"- {result['model']}: {result['seconds']}s, {speed_text}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="查询硅基流动国际版 API 的可用模型、余额和账户状态。"
    )
    parser.add_argument(
        "--api-key",
        help="API Key；不提供时读取 SILICONFLOW_API_KEY，仍没有则交互输入。",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SILICONFLOW_BASE_URL", DEFAULT_BASE_URL),
        help=f"API 根地址（默认：{DEFAULT_BASE_URL}）。",
    )
    parser.add_argument(
        "--type",
        dest="model_type",
        choices=("text", "image", "audio", "video"),
        help="按模型大类筛选。",
    )
    parser.add_argument(
        "--sub-type",
        choices=("chat", "embedding", "reranker", "text-to-image", "image-to-image", "speech-to-text", "text-to-video"),
        help="按模型子类型筛选。",
    )
    parser.add_argument("--no-models", action="store_true", help="只查询余额和账户状态。")
    parser.add_argument("--no-balance", action="store_true", help="只查询模型列表。")
    parser.add_argument("--recommend", action="store_true", help="显示英语翻译和编程的性价比推荐。")
    parser.add_argument(
        "--benchmark",
        nargs="*",
        metavar="MODEL",
        help="测速；可跟一个或多个模型 ID，不填则测试推荐模型。每个模型会产生少量调用费用。",
    )
    parser.add_argument(
        "--benchmark-task",
        choices=("translation", "coding", "short"),
        default="translation",
        help="测速任务类型（默认：translation）。",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 输出。")
    parser.add_argument("--timeout", type=float, default=30.0, help="请求超时秒数。")
    return parser


def _resolve_api_key(provided: str | None) -> str:
    api_key = provided or os.environ.get("SILICONFLOW_API_KEY", "")
    if not api_key:
        # input() supports paste in the Windows console. getpass() reads one
        # character at a time there, which often prevents Ctrl+V/right-click paste.
        api_key = input("SiliconFlow API Key (可直接粘贴): ").strip()
    if not api_key:
        raise ValueError("未提供 API Key。")
    return api_key


def _print_text(info: dict[str, Any] | None, models: list[dict[str, Any]] | None) -> None:
    print("SiliconFlow International API")
    if info is not None:
        print(f"Account : {info.get('name') or info.get('email') or info.get('id') or '-'}")
        print(f"Status  : {info.get('status') or '-'}")
        print(f"Balance : {info.get('balance', '-')}" )
        print(f"Charged : {info.get('chargeBalance', '-')}" )
        print(f"Total   : {info.get('totalBalance', '-')}" )
    if models is not None:
        print(f"Models  : {len(models)}")
        for model in sorted(models, key=lambda item: str(item.get("id", "")).casefold()):
            model_id = model.get("id", "(unknown)")
            model_type = model.get("object", "model")
            print(f"- {model_id} [{model_type}]")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.no_models and args.no_balance:
        parser.error("不能同时使用 --no-models 和 --no-balance。")
    if args.benchmark is not None and args.no_models:
        parser.error("测速需要模型列表，不能同时使用 --benchmark 和 --no-models。")
    try:
        api_key = _resolve_api_key(args.api_key)
        info = None if args.no_balance else fetch_user_info(args.base_url, api_key, args.timeout)
        need_models = not args.no_models or args.recommend or args.benchmark is not None
        models = fetch_models(
            args.base_url, api_key, args.timeout, args.model_type, args.sub_type
        ) if need_models else None

        report = recommendation_report(models) if args.recommend else None
        benchmark_results = None
        if args.benchmark is not None:
            selected = args.benchmark
            if not selected:
                if args.benchmark_task == "coding":
                    selected = list(CODING_RECOMMENDATIONS)
                elif args.benchmark_task == "translation":
                    selected = list(TRANSLATION_RECOMMENDATIONS)
                else:
                    selected = list(dict.fromkeys(TRANSLATION_RECOMMENDATIONS + CODING_RECOMMENDATIONS))
                # Do not spend a request on a recommendation that this key
                # cannot actually access. Explicit model IDs are still tested
                # as requested so the API can report the exact failure.
                available_ids = {str(model.get("id")) for model in (models or [])}
                selected = [model for model in selected if model in available_ids]
            print(f"Benchmarking {len(selected)} model(s); this sends a small paid request per model...")
            benchmark_results = []
            for model in selected:
                try:
                    benchmark_results.append(
                        benchmark_model(args.base_url, api_key, model, args.timeout, args.benchmark_task)
                    )
                except (SiliconFlowAPIError, OSError, TimeoutError) as exc:
                    benchmark_results.append({"model": model, "error": str(exc)})

        if args.as_json:
            print(json.dumps({
                "account": info,
                "models": models,
                "recommendations": report,
                "benchmarks": benchmark_results,
            }, ensure_ascii=False, indent=2))
        else:
            _print_text(info, models)
            if report is not None:
                _print_recommendations(report)
            if benchmark_results is not None:
                _print_benchmarks(benchmark_results)
        return 0
    except (SiliconFlowAPIError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
