"""Manage bilingual research topics and AI-generated related terms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_config import DEFAULT_SETTINGS_PATH, AIServiceConfig
from ai_service import AIService


ROOT = Path(__file__).resolve().parent
TOPICS_PATH = ROOT / "topics.json"


def load_topics(path: Path = TOPICS_PATH) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_topics(topics: list[dict], path: Path = TOPICS_PATH) -> None:
    path.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")


def topic_context(topics: list[dict] | None = None) -> str:
    rows = topics if topics is not None else load_topics()
    lines: list[str] = []
    for topic in rows:
        name = topic.get("name_zh", "")
        zh = ", ".join(topic.get("keywords_zh", []))
        en = ", ".join(topic.get("keywords_en", []))
        related = ", ".join(topic.get("related_topics", []))
        lines.append(f"- {name}: Chinese={zh}; English={en}; Related={related}")
    return "\n".join(lines)


def expand_and_save(names: list[str], path: Path = TOPICS_PATH) -> list[dict]:
    config = AIServiceConfig.from_env()
    if not config.is_active:
        raise RuntimeError("AI is not configured. Run 'python ai_setup.py setup' first.")
    expanded = AIService(config).expand_topics(names).get("topics", [])
    if not isinstance(expanded, list):
        raise RuntimeError("AI returned an invalid topics response")
    current = load_topics(path)
    by_name = {item.get("name_zh"): item for item in current if item.get("name_zh")}
    for item in expanded:
        if isinstance(item, dict) and item.get("name_zh"):
            by_name[item["name_zh"]] = item
    result = list(by_name.values())
    save_topics(result, path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage bilingual research topics")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list saved topics")
    add = sub.add_parser("add", help="expand and save one or more topics")
    add.add_argument("topics", nargs="+", help="Chinese topic names")
    remove = sub.add_parser("remove", help="remove topics by Chinese name")
    remove.add_argument("topics", nargs="+")
    args = parser.parse_args()

    if args.command == "list":
        print(topic_context())
    elif args.command == "add":
        result = expand_and_save(args.topics)
        print(f"Saved {len(result)} topic(s) to {TOPICS_PATH}")
    else:
        names = set(args.topics)
        result = [item for item in load_topics() if item.get("name_zh") not in names]
        save_topics(result)
        print(f"Saved {len(result)} topic(s) to {TOPICS_PATH}")


if __name__ == "__main__":
    main()
