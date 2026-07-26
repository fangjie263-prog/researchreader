from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from ai_config import AIServiceConfig


class AIServiceError(Exception):
    """Raised when an AI provider request fails."""


@dataclass(frozen=True)
class BenchmarkResult:
    model: str
    status: str
    latency: float | None = None
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AIService:
    """Small standard-library client for OpenAI-compatible APIs."""

    def __init__(self, config: AIServiceConfig) -> None:
        self._config = config

    def summarize(self, text: str, topic_context: str = "", max_tokens: int = 300, timeout: int = 60) -> str:
        system = (
            "You are a concise financial-news analyst. Return ONLY valid JSON with exactly "
            "these keys: summary, investment_relevance, matched_topics. "
            "summary must be 2-3 sentences, investment_relevance must be an integer 1-5, "
            "and matched_topics must be an array. Do not use markdown or code fences."
        )
        if topic_context:
            system += "\nConfigured research topics:\n" + topic_context
        result = self._chat(system, text, max_tokens=max_tokens, timeout=timeout)
        return result["choices"][0]["message"]["content"].strip()

    def translate_article(self, article: dict[str, Any]) -> dict[str, Any]:
        source = {
            "title": article.get("title", ""),
            "subtitle": article.get("subtitle", ""),
            "annotation": article.get("annotation", ""),
            "byline": article.get("byline", ""),
            "paragraphs": article.get("paragraphs", []),
        }
        system = (
            "You are a professional financial-news translator. Translate the supplied article "
            "to natural Traditional Chinese. Preserve names, numbers, tickers, quotations and "
            "paragraph order. Return ONLY valid JSON with exactly these keys: title, subtitle, "
            "annotation, byline, paragraphs. paragraphs must be an array of strings."
        )
        return self._chat_json(system, json.dumps(source, ensure_ascii=False), max_tokens=4000)

    def list_models(self) -> list[dict[str, Any]]:
        """Return models from the provider's standard /models endpoint."""
        result = self._request_json(self._config.base_url.rstrip("/") + "/models", timeout=30)
        models = result.get("data", [])
        return [item for item in models if isinstance(item, dict) and item.get("id")]

    def benchmark_model(self, model: str, timeout: int = 30) -> dict[str, Any]:
        """Test one model; every failure becomes FAILED instead of an exception."""
        started = time.perf_counter()
        config = AIServiceConfig(
            enabled=self._config.enabled,
            api_key=self._config.api_key,
            base_url=self._config.base_url,
            model=model,
            endpoint=self._config.endpoint,
        )
        try:
            AIService(config).summarize("Reply with the single word OK.", max_tokens=8, timeout=timeout)
            return BenchmarkResult(model, "PASS", round(time.perf_counter() - started, 3)).as_dict()
        except AIServiceError as exc:
            message = str(exc)
            if "timed out" in message.lower() or "timeout" in message.lower():
                message = "Timeout"
            return BenchmarkResult(model, "FAILED", None if message == "Timeout" else round(time.perf_counter() - started, 3), message).as_dict()
        except (socket.timeout, TimeoutError) as exc:
            return BenchmarkResult(model, "FAILED", None, "Timeout").as_dict()
        except Exception as exc:
            return BenchmarkResult(model, "FAILED", round(time.perf_counter() - started, 3), str(exc)).as_dict()

    def recommend_model(self, model_ids: list[str] | None = None, timeout: int = 30) -> dict[str, Any]:
        """Recommend the fastest model that passes the real chat test."""
        ids = model_ids or [item["id"] for item in self.list_models()]
        results: list[dict[str, Any]] = []
        for model in ids:
            try:
                results.append(self.benchmark_model(model, timeout=timeout))
            except Exception as exc:
                # Keep the queue moving even if a custom benchmark implementation fails.
                results.append(BenchmarkResult(model, "FAILED", None, str(exc)).as_dict())
        usable = sorted((item for item in results if item["status"] == "PASS"), key=lambda item: item["latency"])
        return {"recommended": usable[0]["model"] if usable else "", "results": results}

    def expand_topics(self, topics: list[str]) -> dict[str, Any]:
        system = (
            "You are a bilingual financial research taxonomy assistant. Return ONLY valid JSON "
            "with key topics. Each item must contain name_zh, keywords_zh, keywords_en, "
            "and related_topics. Generate useful search terms, synonyms, abbreviations, "
            "companies, technologies and adjacent concepts."
        )
        return self._chat_json(system, json.dumps({"topics": topics}, ensure_ascii=False), max_tokens=1800)

    def screen_article(self, title: str, excerpt: str, topic_context: str) -> dict[str, Any]:
        """Screen a topic-matched article before spending tokens on a summary."""
        system = (
            "You are a financial research reading-list editor. Return ONLY valid JSON with "
            "exactly these keys: recommend, priority, matched_topics, reason_zh, reason_en, "
            "summary_zh, summary_en. recommend is boolean; priority is integer 1-5. "
            "Only write summaries when recommend is true; otherwise use empty strings. "
            "Keep both summaries concise (2-3 sentences), never translate the full article. "
            "Judge relevance to the configured topics, investment usefulness, novelty and urgency."
        )
        user = json.dumps({
            "topics": topic_context,
            "title": title,
            "excerpt": excerpt[:3500],
        }, ensure_ascii=False)
        return self._chat_json(system, user, max_tokens=700)

    def _chat(self, system: str, user: str, max_tokens: int, timeout: int = 60) -> dict[str, Any]:
        url = self._config.base_url.rstrip("/") + self._config.endpoint
        payload = {
            "model": self._config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._config.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            if not result.get("choices"):
                raise ValueError("no choices in response")
            return result
        except (urllib.error.URLError, socket.timeout, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIServiceError(str(exc)) from exc

    def _chat_json(self, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        content = self._chat(system, user, max_tokens)["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AIServiceError(f"invalid JSON response: {exc}") from exc
        if not isinstance(parsed, dict):
            raise AIServiceError("JSON response is not an object")
        return parsed

    def _request_json(self, url: str, timeout: int) -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self._config.api_key}"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            if not isinstance(result, dict):
                raise ValueError("API response is not an object")
            return result
        except (urllib.error.URLError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise AIServiceError(str(exc)) from exc
