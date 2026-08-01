"""File-based prompt loading and simple template expansion."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPT_DIR = ROOT / "prompts"
_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class PromptManager:
    @staticmethod
    def load(name: str, variables: dict[str, object] | None = None) -> str:
        path = PROMPT_DIR / f"{name}.md"
        if not path.is_file():
            raise FileNotFoundError(f"Prompt not found: {name}")
        text = path.read_text(encoding="utf-8")
        if variables is None:
            return text
        missing = sorted({key for key in _VARIABLE.findall(text) if key not in variables})
        if missing:
            raise KeyError(f"Missing prompt variables: {', '.join(missing)}")
        return _VARIABLE.sub(lambda match: str(variables[match.group(1)]), text)

    @staticmethod
    def version(prompt: str) -> str:
        first = prompt.splitlines()[0].strip() if prompt.splitlines() else ""
        return first.split(":", 1)[1].strip() if first.lower().startswith("version:") else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview a ResearchReader prompt")
    parser.add_argument("name")
    args = parser.parse_args()
    try:
        prompt = PromptManager.load(args.name)
    except FileNotFoundError as exc:
        print(exc)
        return 1
    variables = sorted(set(_VARIABLE.findall(prompt)))
    print("Prompt:\n" + prompt)
    print("Variables:\n" + "\n".join(variables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
