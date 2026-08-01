"""Generate article-level investment research intelligence."""
from __future__ import annotations

import json
from typing import Any

from ai_config import AIServiceConfig
from ai_service import AIService, AIServiceError
from models import Article, ResearchNote
from prompt_context import PromptContext
from prompt_manager import PromptManager


class ResearchNoteError(RuntimeError):
    """Raised when an investment note cannot be generated."""


class ResearchNoteGenerator:
    def __init__(self, service: AIService | None = None) -> None:
        if service is None:
            config = AIServiceConfig.from_env()
            if not config.is_active:
                raise ResearchNoteError("AI is not configured")
            service = AIService(config)
        self.service = service

    def generate(self, article: Article | dict[str, Any]) -> ResearchNote:
        context = PromptContext.from_article(article)
        prompt = PromptManager.load("investment", context)
        user = json.dumps(context, ensure_ascii=False)
        try:
            data = self.service._chat_json(prompt, user, max_tokens=1200)
            if not isinstance(data, dict):
                raise ResearchNoteError("Research note response must be a JSON object")
            return ResearchNote.from_dict(data)
        except ResearchNoteError:
            raise
        except Exception as exc:
            raise ResearchNoteError(f"Research note generation failed: {exc}") from exc


def render_markdown(note: ResearchNote) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) or "- None identified"
    questions = "\n".join(f"{index}. {item}" for index, item in enumerate(note.follow_up_questions, 1)) or "1. None"
    return f"""# Investment Research Note

## Executive Summary

{note.summary}

## Investment Takeaway

{note.investment_takeaway}

## Market Impact

{note.market_impact}

## Companies Mentioned

{bullets(note.companies)}

## Industries

{bullets(note.industries or note.sectors)}

## Countries

{bullets(note.countries)}

## Risks

{bullets(note.risks)}

## Opportunities

{bullets(note.opportunities)}

## Questions Worth Researching

{questions}

## Confidence

{note.confidence}
"""
