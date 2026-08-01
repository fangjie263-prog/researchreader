# ResearchReader v2.0.0

## Overview

ResearchReader v2.0.0 completes the platform architecture upgrade. It establishes the Core Pipeline, AI Pipeline, Article Engine, Prompt Framework, AI Quality Engine, Workspace, Manifest, and Research Package foundations for future Research Intelligence features.

## Highlights

- Stable multi-magazine EPUB/PDF processing
- Unified `Article` data model and `ArticleFactory`
- Configurable file-based Prompt Framework
- AI Quality Engine and auditable reports
- Article-level Research Note generation
- Bilingual Research Package generation
- Workspace and Manifest support
- Core / AI Pipeline separation
- Multi-magazine queue processing
- Backward-compatible command-line workflows

## Architecture

```text
EPUB / PDF / HTML
        ↓
Core Pipeline
        ↓
Article
        ↓
articles.json
        ↓
AI Pipeline
        ↓
Research Package
```

## Major Components

- Parser
- Cleaner
- ArticleMerger
- ContinuationResolver
- Quality Filter
- Article
- ArticleFactory
- PromptManager
- PromptContext
- AIQualityValidator
- ResearchNoteGenerator
- WorkspaceManager
- CorePipeline
- AIPipeline

## Compatibility

The release keeps `run_wsj.bat`, `wsj_queue.py`, legacy CLI commands, existing HTML output, and the Translation Pipeline available. Existing workflows remain usable.

## Project Statistics

- Python files: 49 (excluding local caches and temporary directories)
- Prompt files: 6
- Dataclass declarations: 15
- Pipeline classes: 2
- Automated tests: 98
- Test result: `Ran 98 tests` / `OK`

## Future Direction

Future releases will focus on Research Intelligence, including Research Modes, Magazine Intelligence, Portfolio Intelligence, and Knowledge Base capabilities.
