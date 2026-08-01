"""Self-contained magazine workspace and manifest management."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WorkspaceManager:
    @staticmethod
    def create(root: str | Path, publication: str, issue_date: str = "", language: str = "en", article_count: int = 0, quality_score: int = 0) -> Path:
        path = Path(root)
        for name in ("images", "recommendations", "packages", "logs"):
            (path / name).mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": "2.1", "publication": publication, "issue_date": issue_date,
            "generated_at": datetime.now(timezone.utc).isoformat(), "language": language,
            "article_count": article_count, "quality_score": quality_score, "workspace_version": "1.0",
            "files": {"articles": "articles.json", "html": "daily.html", "markdown": "extracted_articles.md",
                      "images": "images/", "recommendations": "recommendations/", "packages": "packages/", "logs": "logs/"},
        }
        (path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def load(root: str | Path) -> dict[str, Any]:
        path = Path(root)
        return json.loads((path / "manifest.json").read_text(encoding="utf-8"))

    @staticmethod
    def find_latest(output_root: str | Path = "output") -> Path | None:
        workspaces = [path for path in Path(output_root).iterdir() if path.is_dir() and (path / "manifest.json").is_file()] if Path(output_root).is_dir() else []
        return max(workspaces, key=lambda path: (path / "manifest.json").stat().st_mtime) if workspaces else None
