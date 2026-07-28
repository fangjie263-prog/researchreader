"""Manage user research topics and AI-maintained aliases."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ai_config import AIServiceConfig
from ai_service import AIService


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
LEGACY_TOPICS_PATH = ROOT / "topics.json"
TOPICS_PATH = CONFIG_DIR / "topics.json"
ALIASES_PATH = CONFIG_DIR / "aliases.json"
ALIASES_CANDIDATE_PATH = CONFIG_DIR / "aliases_candidate.json"
ALIASES_DIFF_PATH = CONFIG_DIR / "aliases.diff.md"
HISTORY_DIR = CONFIG_DIR / "history"
KNOWLEDGE_HEALTH_REPORT_PATH = CONFIG_DIR / "knowledge_health_report.md"
WHITELIST_PATH = CONFIG_DIR / "whitelist.json"
BLACKLIST_PATH = CONFIG_DIR / "blacklist.json"
WEIGHTS_PATH = CONFIG_DIR / "weights.json"
SCHEMA_VERSION = 1
ALIAS_CATEGORIES = ("keywords", "companies", "products", "technologies", "abbreviations")
LEGACY_ALIAS_FIELDS = ("keywords_en", "keywords_zh", "related_topics")


GENERIC_TERMS = {
    "tech",
    "technology",
    "company",
    "market",
    "business",
    "economy",
    "growth",
    "investment",
    "data",
    "model",
}


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _clean_terms(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        term = " ".join(value.strip().split())
        if not term or term.casefold() in GENERIC_TERMS:
            continue
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            result.append(term)
    return result


def _merge_terms(*groups: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for term in _clean_terms(group):
            key = term.casefold()
            if key not in seen:
                seen.add(key)
                result.append(term)
    return result


def _topic_name(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("name_zh", "") or item.get("name", "") or "").strip()
    return ""


def load_topics(path: Path = TOPICS_PATH) -> list[Any]:
    """Load user topics, falling back to the legacy root topics.json."""
    data = _read_json(path, None)
    if isinstance(data, list):
        return data
    legacy = _read_json(LEGACY_TOPICS_PATH, [])
    return legacy if isinstance(legacy, list) else []


def load_topic_names(path: Path = TOPICS_PATH) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in load_topics(path):
        name = _topic_name(item)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def save_topics(topics: list[Any], path: Path = TOPICS_PATH) -> None:
    _write_json(path, topics)


def _empty_alias_topic(updated_at: str | None = None) -> dict[str, Any]:
    return {
        "keywords": [],
        "companies": [],
        "products": [],
        "technologies": [],
        "abbreviations": [],
        "updated_at": updated_at or date.today().isoformat(),
        "source": "AI Refresh",
    }


def _normalize_topic_alias(item: Any, updated_at: str | None = None) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    record = _empty_alias_topic(str(item.get("updated_at") or updated_at or date.today().isoformat()))
    record["source"] = str(item.get("source") or "AI Refresh")
    record["keywords"] = _merge_terms(
        item.get("keywords"),
        item.get("keywords_en"),
        item.get("keywords_zh"),
        item.get("related_topics"),
    )
    for category in ("companies", "products", "technologies", "abbreviations"):
        record[category] = _clean_terms(item.get(category))
    return record


def _alias_topics(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    topics = data.get("topics")
    if isinstance(topics, dict):
        return topics
    return data


def normalize_alias_database(
    data: Any,
    generator: str = "",
    generator_model: str = "",
    generated_at: str | None = None,
) -> dict[str, Any]:
    now_text = generated_at or _now().isoformat()
    raw_topics = _alias_topics(data)
    topics: dict[str, dict[str, Any]] = {}
    for topic, item in raw_topics.items():
        if isinstance(topic, str) and topic.strip():
            topics[topic.strip()] = _normalize_topic_alias(item)
    return {
        "knowledge_version": now_text[:10],
        "generator": generator or (data.get("generator", "") if isinstance(data, dict) else ""),
        "generator_model": generator_model or (data.get("generator_model", "") if isinstance(data, dict) else ""),
        "generated_at": now_text,
        "schema_version": SCHEMA_VERSION,
        "topics": topics,
    }


def load_alias_database(path: Path = ALIASES_PATH) -> dict[str, Any]:
    return normalize_alias_database(_read_json(path, {}))


def load_aliases(path: Path = ALIASES_PATH) -> dict[str, dict[str, Any]]:
    return load_alias_database(path)["topics"]


def save_aliases(aliases: dict[str, dict[str, Any]] | dict[str, Any], path: Path = ALIASES_PATH) -> None:
    _write_json(path, normalize_alias_database(aliases))


def _legacy_aliases() -> dict[str, dict[str, Any]]:
    aliases: dict[str, dict[str, Any]] = {}
    for item in load_topics(LEGACY_TOPICS_PATH):
        if not isinstance(item, dict):
            continue
        name = _topic_name(item)
        if not name:
            continue
        aliases[name] = {
            "keywords": _merge_terms(item.get("keywords_zh"), item.get("keywords_en"), item.get("related_topics")),
            "companies": [],
            "products": [],
            "technologies": [],
            "abbreviations": [],
            "updated_at": item.get("updated_at", ""),
            "source": "Legacy topics.json",
        }
    return aliases


def load_topic_records(
    topics_path: Path = TOPICS_PATH,
    aliases_path: Path = ALIASES_PATH,
) -> list[dict[str, Any]]:
    """Return TopicFilter-compatible records from new aliases or legacy topics."""
    topics = load_topics(topics_path)
    aliases = load_aliases(aliases_path)
    if not aliases:
        aliases = _legacy_aliases()

    records: list[dict[str, Any]] = []
    for item in topics:
        name = _topic_name(item)
        if not name:
            continue
        if isinstance(item, dict) and item.get("keywords_en"):
            alias = item
        else:
            alias = aliases.get(name, {})
        records.append({
            "name_zh": name,
            "keywords_zh": [],
            "keywords_en": _merge_terms(
                alias.get("keywords"),
                alias.get("companies"),
                alias.get("products"),
                alias.get("technologies"),
                alias.get("abbreviations"),
                alias.get("keywords_zh"),
                alias.get("keywords_en"),
            ),
            "related_topics": _clean_terms(alias.get("related_topics")),
        })
    return records


def topic_context(topics: list[Any] | None = None) -> str:
    rows = load_topic_records() if topics is None else [
        {
            "name_zh": _topic_name(topic),
            "keywords_zh": _clean_terms(topic.get("keywords_zh")) if isinstance(topic, dict) else [],
            "keywords_en": _clean_terms(topic.get("keywords_en")) if isinstance(topic, dict) else [],
            "related_topics": _clean_terms(topic.get("related_topics")) if isinstance(topic, dict) else [],
        }
        for topic in topics
    ]
    lines: list[str] = []
    for topic in rows:
        name = topic.get("name_zh", "")
        zh = ", ".join(topic.get("keywords_zh", []))
        en = ", ".join(topic.get("keywords_en", []))
        related = ", ".join(topic.get("related_topics", []))
        lines.append(f"- {name}: Chinese={zh}; English={en}; Related={related}")
    return "\n".join(lines)


def expand_and_save(names: list[str], path: Path = TOPICS_PATH) -> list[str]:
    current = load_topic_names(path)
    for name in names:
        if name not in current:
            current.append(name)
    save_topics(current, path)
    return current


def remove_topics(names: list[str], path: Path = TOPICS_PATH) -> list[str]:
    targets = set(names)
    result = [name for name in load_topic_names(path) if name not in targets]
    save_topics(result, path)
    return result


def _normalise_alias_payload(topics: list[str], payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_aliases = payload.get("aliases", payload)
    if not isinstance(raw_aliases, dict):
        raise RuntimeError("AI returned an invalid aliases response")
    today = date.today().isoformat()
    result: dict[str, dict[str, Any]] = {}
    for topic in topics:
        item = raw_aliases.get(topic, {})
        if not isinstance(item, dict):
            item = {}
        alias = _normalize_topic_alias(item, updated_at=today)
        alias["source"] = str(item.get("source") or "AI Refresh")
        result[topic] = alias
    return result


def build_alias_database(
    topics: dict[str, dict[str, Any]],
    generator: str = "AI",
    generator_model: str = "",
    generated_at: str | None = None,
) -> dict[str, Any]:
    return normalize_alias_database(
        {
            "generator": generator,
            "generator_model": generator_model,
            "generated_at": generated_at or _now().isoformat(),
            "schema_version": SCHEMA_VERSION,
            "topics": topics,
        }
    )


def generate_alias_candidates(
    service: AIService,
    topics_path: Path = TOPICS_PATH,
    aliases_path: Path = ALIASES_PATH,
    candidate_path: Path = ALIASES_CANDIDATE_PATH,
    diff_path: Path = ALIASES_DIFF_PATH,
) -> dict[str, dict[str, Any]]:
    topics = load_topic_names(topics_path)
    current_db = load_alias_database(aliases_path)
    current = current_db["topics"]
    payload = service.refresh_topic_aliases(topics, current_db)
    candidates = _normalise_alias_payload(topics, payload)
    candidate_db = build_alias_database(
        candidates,
        generator=service.__class__.__name__,
        generator_model=getattr(getattr(service, "_config", None), "model", ""),
    )
    _write_json(candidate_path, candidate_db)
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(build_alias_diff(current, candidates), encoding="utf-8")
    return candidates


def _reason_for_added(term: str, category: str) -> str:
    return f"Newly identified {category[:-1] if category.endswith('s') else category} term for current investment research coverage."


def _reason_for_removed(term: str, category: str) -> str:
    return f"No longer present in the latest AI-maintained {category} set; likely obsolete, less used, or too ambiguous."


def build_alias_diff(
    current: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
) -> str:
    lines = ["# Aliases Diff", ""]
    for topic in candidate:
        lines.extend([f"## {topic}", ""])
        for field in ALIAS_CATEGORIES:
            old = set(_clean_terms(current.get(topic, {}).get(field)))
            new = set(_clean_terms(candidate.get(topic, {}).get(field)))
            added = sorted(new - old, key=str.casefold)
            removed = sorted(old - new, key=str.casefold)
            lines.extend([f"### {field}", "", "Added", ""])
            if added:
                for term in added:
                    lines.extend([term, "", "Reason", _reason_for_added(term, field), ""])
            else:
                lines.extend(["None", ""])
            lines.extend(["Removed", ""])
            if removed:
                for term in removed:
                    lines.extend([term, "", "Reason", _reason_for_removed(term, field), ""])
            else:
                lines.extend(["None", ""])
            lines.append("-----------------------------------")
            lines.append("")
    return "\n".join(lines)


def backup_aliases(path: Path = ALIASES_PATH, history_dir: Path = HISTORY_DIR) -> Path | None:
    if not path.exists():
        return None
    history_dir.mkdir(parents=True, exist_ok=True)
    target = history_dir / f"aliases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def apply_alias_candidates(
    selection: str = "all",
    candidate_path: Path = ALIASES_CANDIDATE_PATH,
    aliases_path: Path = ALIASES_PATH,
    selected_topics: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    candidates = load_aliases(candidate_path)
    if selection in {"reject", "n", "no"}:
        return load_aliases(aliases_path)
    if selection in {"selected", "s"}:
        allowed = set(selected_topics or [])
        current = load_aliases(aliases_path)
        for topic in allowed:
            if topic in candidates:
                current[topic] = candidates[topic]
        backup_aliases(aliases_path, HISTORY_DIR)
        save_aliases(current, aliases_path)
        return current
    if selection not in {"all", "a", "y", "yes"}:
        raise ValueError(f"Unknown alias confirmation choice: {selection}")
    backup_aliases(aliases_path, HISTORY_DIR)
    save_aliases(candidates, aliases_path)
    return candidates


def validate_alias_database(data: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if "topics" not in data:
        warnings.append("metadata missing: topics envelope not found; using backward-compatible fallback")
    for field in ("knowledge_version", "generated_at", "generator", "generator_model", "schema_version"):
        if not data.get(field):
            warnings.append(f"metadata missing: {field}")

    raw_topics = _alias_topics(data)
    for topic, item in raw_topics.items():
        if not isinstance(item, dict):
            warnings.append(f"{topic}: topic entry is not an object")
            continue
        known = set(ALIAS_CATEGORIES) | set(LEGACY_ALIAS_FIELDS) | {"updated_at", "source"}
        for key in item:
            if key not in known:
                warnings.append(f"{topic}: unknown category {key}")
        for category in ALIAS_CATEGORIES:
            terms = item.get(category, [])
            if terms == []:
                warnings.append(f"{topic}: empty category {category}")
            cleaned = _clean_terms(terms)
            if isinstance(terms, list) and len(cleaned) != len(terms):
                warnings.append(f"{topic}: duplicate or invalid terms in {category}")
            seen: set[str] = set()
            duplicates: set[str] = set()
            for term in terms if isinstance(terms, list) else []:
                if isinstance(term, str):
                    key = term.strip().casefold()
                    if key in seen:
                        duplicates.add(term.strip())
                    seen.add(key)
            for duplicate in sorted(duplicates, key=str.casefold):
                warnings.append(f"{topic}: duplicate {category} term {duplicate}")
    return warnings


def doctor() -> Path:
    """Reserve the knowledge doctor interface for future health checks."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = _read_json(ALIASES_PATH, {})
    warnings = validate_alias_database(data if isinstance(data, dict) else {})
    lines = [
        "# Knowledge Health Report",
        "",
        "Knowledge Version",
        str(data.get("knowledge_version", "")) if isinstance(data, dict) else "",
        "",
        "Topics",
        str(len(_alias_topics(data))),
        "",
        "Alias Count",
        "Reserved",
        "",
        "Duplicate Count",
        str(sum(1 for warning in warnings if "duplicate" in warning.casefold())),
        "",
        "Empty Topics",
        "Reserved",
        "",
        "Potential Merge",
        "Reserved",
        "",
        "Generic Terms",
        "Reserved",
        "",
        "Warnings",
    ]
    lines.extend(warnings or ["None"])
    KNOWLEDGE_HEALTH_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return KNOWLEDGE_HEALTH_REPORT_PATH


def export_knowledge() -> None:
    raise NotImplementedError("Export interface is reserved for a future phase.")


def refresh(confirm: bool = True) -> dict[str, dict[str, Any]]:
    config = AIServiceConfig.from_env()
    if not config.is_active:
        raise RuntimeError("AI is not configured. Run 'python ai_setup.py setup' first.")
    candidates = generate_alias_candidates(AIService(config))
    print(f"Candidate aliases: {ALIASES_CANDIDATE_PATH}")
    print(f"Diff: {ALIASES_DIFF_PATH}")
    if not confirm:
        return candidates
    choice = input("Accept? [y]es / [a]ll / [s]elected / [n]o: ").strip().casefold()
    if choice in {"", "y", "yes", "a", "all"}:
        return apply_alias_candidates("all")
    if choice in {"s", "selected"}:
        raw = input("Topics to accept, separated by comma: ")
        topics = [item.strip() for item in raw.split(",") if item.strip()]
        return apply_alias_candidates("selected", selected_topics=topics)
    return apply_alias_candidates("reject")


def ensure_config_files() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not TOPICS_PATH.exists():
        save_topics(load_topic_names(), TOPICS_PATH)
    for path, default in (
        (ALIASES_PATH, normalize_alias_database({})),
        (WHITELIST_PATH, []),
        (BLACKLIST_PATH, []),
        (WEIGHTS_PATH, {"title": 20, "subtitle": 10, "body": 5, "related_topic": 3, "repeated_keyword": 1}),
    ):
        if not path.exists():
            _write_json(path, default)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage research topics and AI-maintained aliases")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list saved topics")
    add = sub.add_parser("add", help="save one or more user topic names")
    add.add_argument("topics", nargs="+", help="topic names")
    remove = sub.add_parser("remove", help="remove topics by name")
    remove.add_argument("topics", nargs="+")
    refresh_cmd = sub.add_parser("refresh", help="generate AI alias candidates and confirm before applying")
    refresh_cmd.add_argument("--no-confirm", action="store_true", help="only write aliases_candidate.json and aliases.diff.md")
    sub.add_parser("doctor", help="reserved knowledge health check interface")
    sub.add_parser("export", help="reserved knowledge export interface")
    args = parser.parse_args()

    ensure_config_files()
    if args.command == "list":
        print(topic_context())
    elif args.command == "add":
        result = expand_and_save(args.topics)
        print(f"Saved {len(result)} topic(s) to {TOPICS_PATH}")
    elif args.command == "remove":
        result = remove_topics(args.topics)
        print(f"Saved {len(result)} topic(s) to {TOPICS_PATH}")
    elif args.command == "refresh":
        result = refresh(confirm=not args.no_confirm)
        print(f"Prepared {len(result)} topic alias set(s)")
    elif args.command == "doctor":
        report = doctor()
        print(f"Knowledge doctor is reserved; wrote scaffold report: {report}")
    else:
        print("Export interface is reserved for a future phase.")


if __name__ == "__main__":
    main()
