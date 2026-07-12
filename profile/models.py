"""Frozen dataclasses that represent a Research Profile."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Research:
    """User-defined research interests.

    Contains only raw terms entered by the user.  Synonym expansion
    and concept enrichment are performed by the AI layer at runtime,
    never stored in the profile itself.
    """

    companies: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    technology: tuple[str, ...] = ()
    macroeconomics: tuple[str, ...] = ()
    people: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict | None) -> Research:
        if data is None:
            return cls()
        return cls(
            companies=tuple(data.get("companies", [])),
            industries=tuple(data.get("industries", [])),
            technology=tuple(data.get("technology", [])),
            macroeconomics=tuple(data.get("macroeconomics", [])),
            people=tuple(data.get("people", [])),
            regions=tuple(data.get("regions", [])),
        )


@dataclass(frozen=True, slots=True)
class Exclusions:
    """Terms and topics to exclude from results."""

    topics: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict | None) -> Exclusions:
        if data is None:
            return cls()
        return cls(topics=tuple(data.get("topics", [])))


@dataclass(frozen=True, slots=True)
class Presentation:
    """Controls how output is rendered."""

    summary_language: str = "bilingual"
    chinese_first: bool = True
    show_summary: bool = True
    show_score: bool = True

    @classmethod
    def from_dict(cls, data: dict | None) -> Presentation:
        if data is None:
            return cls()
        lang = data.get("language", {})
        return cls(
            summary_language=str(lang.get("summary", "bilingual")),
            chinese_first=bool(lang.get("chinese_first", True)),
            show_summary=bool(data.get("html", {}).get("show_summary", True)),
            show_score=bool(data.get("html", {}).get("show_score", True)),
        )


@dataclass(frozen=True, slots=True)
class Processing:
    """Runtime constraints for article processing."""

    max_articles: int = 100
    minimum_score: int = 3

    @classmethod
    def from_dict(cls, data: dict | None) -> Processing:
        if data is None:
            return cls()
        return cls(
            max_articles=int(data.get("max_articles", 100)),
            minimum_score=int(data.get("minimum_score", 3)),
        )


@dataclass(frozen=True, slots=True)
class Profile:
    """Top-level research profile.

    A profile is immutable once constructed.  It holds the user's
    research intent, output preferences, and processing constraints.
    """

    name: str
    research: Research
    exclusions: Exclusions
    presentation: Presentation
    processing: Processing

    @classmethod
    def from_dict(cls, data: dict) -> Profile:
        """Build a Profile from a parsed YAML dictionary."""
        if not data:
            raise ValueError("Profile data must not be empty.")
        prof = data.get("profile", {})
        if not prof:
            raise ValueError("Missing 'profile' section in YAML.")
        name = str(prof.get("name", "Untitled"))
        if not name.strip():
            raise ValueError("Profile 'name' must not be empty.")
        return cls(
            name=name.strip(),
            research=Research.from_dict(data.get("research")),
            exclusions=Exclusions.from_dict(data.get("exclusions")),
            presentation=Presentation.from_dict(data.get("presentation")),
            processing=Processing.from_dict(data.get("processing")),
        )
