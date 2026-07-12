from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ai_config import AIServiceConfig


class AIServiceError(Exception):
    """Raised when the AI service call fails."""


class AIService:
    """Thin HTTP client for any OpenAI-compatible chat completions API.

    Uses only the Python standard library -- no new dependencies.
    """

    def __init__(self, config: AIServiceConfig) -> None:
        self._config = config

    def summarize(self, text: str) -> str:
        """Send *text* to the model and return the raw response string.

        Raises :exc:`AIServiceError` on any failure.
        """

        url = self._config.base_url.rstrip("/") + self._config.endpoint

        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a concise financial-news analyst.\n\n"
                        "Return ONLY a valid JSON object with exactly this schema:\n\n"
                        "{\n"
                        '  "summary": "<2-3 sentence summary>",\n'
                        '  "investment_relevance": <integer 1-5>\n'
                        "}\n\n"
                        "Do not output markdown.\n"
                        "Do not use code fences.\n"
                        "Do not output explanations.\n"
                        "Return only the JSON object."
                    ),
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
            "max_tokens": 300,
        }

        body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._config.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))

        except urllib.error.URLError as exc:
            raise AIServiceError(str(exc)) from exc

        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise AIServiceError(f"unexpected response: {exc}") from exc

        choices: list[dict] = result.get("choices", [])

        if not choices:
            raise AIServiceError("no choices in response")

        return choices[0]["message"]["content"].strip()