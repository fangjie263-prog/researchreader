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
        """Send *text* to the model and return the summary string.

        Raises :exc:`AIServiceError` on any failure.
        """

        print(">>> ENTER AIService.summarize()")

        url = self._config.base_url.rstrip("/") + self._config.endpoint

        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a concise financial-news analyst. "
                        "Summarise the provided article in 2-3 sentences. "
                        "Do not add commentary or disclaimers."
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

        print(">>> Sending AI request...")
        print(f"URL   : {url}")
        print(f"Model : {self._config.model}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                print(">>> AI response received.")

                result = json.loads(
                    resp.read().decode("utf-8")
                )

        except urllib.error.URLError as exc:
            print(">>> AI request failed.")
            print(f"{type(exc).__name__}: {exc}")
            raise AIServiceError(str(exc)) from exc

        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            print(">>> AI request failed.")
            print(f"{type(exc).__name__}: {exc}")
            raise AIServiceError(
                f"unexpected response: {exc}"
            ) from exc

        choices: list[dict] = result.get("choices", [])

        if not choices:
            print(">>> Response contains no choices.")
            raise AIServiceError("no choices in response")

        summary = choices[0]["message"]["content"].strip()

        print(">>> Summary (first 120 chars):")
        print(summary[:120])

        return summary