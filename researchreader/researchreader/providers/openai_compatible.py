from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from ..config import ProviderConfig
from .base import ProviderError, ProviderTestResult


@dataclass(frozen=True)
class _ResponseTimings:
    first_token_latency_ms: float
    total_response_time_ms: float


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig, timeout_seconds: float = 30.0) -> None:
        self.config = config
        self._timeout_seconds = timeout_seconds

    def list_models(self) -> list[str]:
        payload = self._request_json("GET", "/models")
        data = payload.get("data", [])
        if not isinstance(data, list):
            raise ProviderError("models response does not contain a data list")

        models: list[str] = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                models.append(item["id"])
        return models

    def measure_first_token_latency(self) -> float:
        return self._measure_response_timings().first_token_latency_ms

    def _measure_response_timings(self) -> _ResponseTimings:
        request_body = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "temperature": 0,
            "max_tokens": 8,
            "stream": True,
        }
        request = self._build_request("POST", "/chat/completions", request_body)
        started_at = time.perf_counter()
        first_token_latency_ms: float | None = None
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                while True:
                    raw_line = response.readline()
                    if not raw_line:
                        break
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ").strip()
                    if data == "[DONE]":
                        break
                    if first_token_latency_ms is None and self._contains_stream_token(data):
                        first_token_latency_ms = (time.perf_counter() - started_at) * 1000
        except urllib.error.HTTPError as error:
            raise ProviderError(_format_http_error(error)) from error
        except urllib.error.URLError as error:
            raise ProviderError(f"connection failed: {error.reason}") from error

        total_response_time_ms = (time.perf_counter() - started_at) * 1000
        if first_token_latency_ms is None:
            raise ProviderError("stream ended before the first token was received")
        return _ResponseTimings(
            first_token_latency_ms=first_token_latency_ms,
            total_response_time_ms=total_response_time_ms,
        )

    def test(self) -> ProviderTestResult:
        errors = self.config.validate()
        if errors:
            return ProviderTestResult(
                provider_name=self.config.name,
                display_name=self.config.display_name,
                model=self.config.model,
                ok=False,
                configuration_ok=False,
                errors=tuple(errors),
            )

        connectivity_ok = False
        model_available = False
        latency_ms: float | None = None
        total_time_ms: float | None = None

        try:
            models = self.list_models()
            connectivity_ok = True
            model_available = self.config.model in models
            if not model_available:
                errors.append(f"configured model is not available: {self.config.model}")
        except ProviderError as error:
            errors.append(str(error))

        if connectivity_ok and model_available:
            try:
                timings = self._measure_response_timings()
                latency_ms = timings.first_token_latency_ms
                total_time_ms = timings.total_response_time_ms
            except ProviderError as error:
                errors.append(f"first-token latency test failed: {error}")

        return ProviderTestResult(
            provider_name=self.config.name,
            display_name=self.config.display_name,
            model=self.config.model,
            ok=not errors,
            configuration_ok=True,
            connectivity_ok=connectivity_ok,
            model_available=model_available,
            first_token_latency_ms=latency_ms,
            total_response_time_ms=total_time_ms,
            errors=tuple(errors),
        )

    def _request_json(self, method: str, path: str) -> dict:
        request = self._build_request(method, path)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            raise ProviderError(_format_http_error(error)) from error
        except urllib.error.URLError as error:
            raise ProviderError(f"connection failed: {error.reason}") from error

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as error:
            raise ProviderError("response is not valid JSON") from error
        if not isinstance(payload, dict):
            raise ProviderError("response JSON must be an object")
        return payload

    def _build_request(self, method: str, path: str, body: dict | None = None) -> urllib.request.Request:
        api_key = self.config.resolved_api_key
        if not api_key:
            raise ProviderError(f"missing API key environment variable: {self.config.api_key_env}")

        url = self.config.base_url.rstrip("/") + path
        data = None
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        return urllib.request.Request(url=url, data=data, headers=headers, method=method)

    def _contains_stream_token(self, data: str) -> bool:
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return False
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list):
            return False
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict) and delta.get("content"):
                return True
        return False


def _format_http_error(error: urllib.error.HTTPError) -> str:
    try:
        body = error.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    message = f"HTTP {error.code}: {error.reason}"
    if body:
        message = f"{message}; {body[:500]}"
    return message
