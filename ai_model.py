from __future__ import annotations

from dataclasses import dataclass, field
from typing import NotRequired, TypedDict


class ArticleAnalysis(TypedDict, total=False):
    """Analysis results attached to a single WSJ article."""

    importance: int  # 1-5
    summary_zh: str  # 150-250 Chinese characters
    why_read: str    # 2-3 sentences, investor perspective
    translation_zh: NotRequired[str]  # full Chinese translation (only if enabled)


@dataclass
class AIConfig:
    """Configuration for the AI reading layer."""

    enabled: bool = True
    translate_full: bool = False
