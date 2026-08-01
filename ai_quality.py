"""Validation and audit records for AI-generated structured results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from models import AIQualityReport, ResearchNote
from prompt_manager import PromptManager


REQUIRED_FIELDS = {
    "investment": ("summary", "investment_takeaway", "confidence", "companies", "industries", "countries", "risks", "opportunities"),
}


class AIQualityValidator:
    def validate(self, result: Any, task_name: str, *, provider: str = "unknown", model: str = "unknown",
                 prompt_name: str | None = None, latency_ms: int = 0, usage: dict[str, Any] | None = None) -> AIQualityReport:
        data = result.to_dict() if isinstance(result, ResearchNote) else result
        warnings: list[str] = []
        if not isinstance(data, dict):
            warnings.append("Provider returned no valid JSON object")
            data = {}
        for field in REQUIRED_FIELDS.get(task_name, ("summary",)):
            if field not in data:
                warnings.append(f"Missing field: {field}")
            elif field in {"summary", "investment_takeaway", "confidence"} and not str(data[field]).strip():
                warnings.append(f"Empty field: {field}")
        if len(str(data.get("summary", "")).strip()) < 20:
            warnings.append("summary is shorter than 20 characters")
        prompt_name = prompt_name or task_name
        prompt = PromptManager.load(prompt_name)
        version = PromptManager.version(prompt)
        if not version:
            warnings.append("Prompt version missing")
        usage = usage or {}
        success = not warnings
        score = max(0, 100 - len(warnings) * 10)
        return AIQualityReport(task_name, provider, model, prompt_name, version, latency_ms,
                               usage.get("prompt_tokens"), usage.get("completion_tokens"),
                               usage.get("total_tokens"), success, warnings, score)


def write_audit(report: AIQualityReport, output: Path | str) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an AI result JSON")
    parser.add_argument("result")
    parser.add_argument("--task", default="investment")
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.result).read_text(encoding="utf-8"))
        report = AIQualityValidator().validate(data, args.task)
    except Exception as exc:
        print(f"FAILED\nReason: {exc}")
        return 1
    print("PASS" if report.success else "FAILED")
    print(f"Score: {report.score}")
    print(f"Warnings: {len(report.warnings)}")
    if report.warnings:
        print("\n".join(report.warnings))
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
