"""Canonical article data model for future pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4
from typing import Any


@dataclass
class Article:
    uuid: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    subtitle: str = ""
    author: str = ""
    source: str = ""
    paragraphs: list[Any] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0
    warnings: list[str] = field(default_factory=list)
