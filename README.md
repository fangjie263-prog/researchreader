# ResearchReader

ResearchReader is an open-source command-line toolkit for collecting, parsing, translating, filtering, and reading financial news and publications.

License: [MIT](LICENSE)

The MIT license covers original code in this repository. Third-party dependencies, downloaded EPUB/PDF files, scraped website content, API services, and model outputs remain subject to their own licenses, copyrights, and terms of service.

## Current capabilities

### HKEJ news to HTML

```powershell
run_hkej.bat
python hkej_to_html.py path\to\hkej_news.txt
python hkej_to_html.py path\to\hkej_news.json
```

### WSJ / EPUB batch processing

Place EPUB files in `books\` and run `run_wsj.bat`. Each book is written to its own directory:

```text
output\book-name\
├── daily.html
├── extracted_articles.md
├── translation_progress.json
└── images\
```

The workflow supports article and image extraction, duplicate removal, fragment merging, HTML/Markdown output, optional OpenAI-compatible translation, resumable progress, retries, and per-book error reporting.

Optional settings:

```bat
set WSJ_API_DELAY=5
set WSJ_API_RETRIES=3
set WSJ_ANALYZE=1
set WSJ_TRANSLATE=1
run_wsj.bat
```

By default, the workflow extracts original text and generates HTML/Markdown without translation or per-article analysis.

### PDF batch processing

Place text-based PDFs in `books\` and run `run_pdf.bat`. The current workflow uses selectable text extraction and produces copyable HTML and Markdown. Scanned PDFs require a separate OCR workflow.

```powershell
python pdf_reader.py path\to\document.pdf
python pdf_reader.py path\to\document.pdf --output output\document.html
```

### AI service and benchmarking

```powershell
python ai_setup.py setup
python ai_setup.py test
python ai_setup.py test --timeout 15 --top 5
python ai_setup.py test --model DeepSeek-V4-Flash
python ai_setup.py test --provider hcnsec
```

OpenAI-compatible providers can also be configured with `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`, and `AI_ENDPOINT`. Never commit API keys.

### Research topics and recommendations

```powershell
python topic_manager.py add "人工智能" "半导体"
python topic_manager.py list
python topic_manager.py remove "半导体"
python research_digest.py
```

Local topic filtering runs before short candidate excerpts are sent to the AI service. Recommendations are written as Markdown, HTML, and JSON.

### Research packages

```powershell
python research_package.py article_001
python research_package.py article_001 article_005
python research_package.py --top 5
```

Packages can contain the original article, Chinese translation, bilingual Markdown, metadata, investment research notes, and AI quality reports when AI is configured.

### Core / AI pipelines and workspaces

```powershell
run_reader.bat path\to\book.epub
python ai_pipeline.py output\workspace --recommend
```

The Core Pipeline produces a workspace containing `articles.json`, HTML, Markdown, images, recommendations, packages, logs, and `manifest.json`. The AI Pipeline consumes normalized article JSON rather than reading EPUB files directly.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Automated tests

```powershell
python -m unittest discover -s tests -v
```

The suite covers EPUB merging, PDF extraction, HTML escaping, HKEJ conversion, AI configuration and benchmarking, topic filtering, Article Engine compatibility, Prompt Framework, Research Notes, AI Quality, and Workspace behavior.

## Project layout

```text
wsj_reader.py       EPUB parsing and HTML/Markdown output
wsj_queue.py        EPUB batch processing and resumable workflow
pdf_reader.py       PDF text extraction and HTML output
pdf_queue.py        PDF batch processing
hkej_to_html.py     HKEJ TXT/JSON conversion
ai_service.py       OpenAI-compatible API client
ai_setup.py         AI settings and model benchmarking
topic_manager.py    Research topic management
research_digest.py  Topic screening and reading recommendations
article_factory.py  Legacy dict / Article conversion
prompt_manager.py   File-based prompt loading
ai_quality.py       AI result validation and audit
research_note.py    Article-level investment research notes
workspace.py        Workspace and manifest management
pipelines/          Core and AI pipeline orchestration
prompts/            Versioned prompt templates
tests/              Automated tests
books/              Local EPUB/PDF inputs
output/             Local generated outputs
```

## Known limitations

- Scanned PDFs require OCR, which is not currently included.
- Complex magazine layouts may not be reproduced exactly; the priority is selectable text and readable paragraphs.
- Copyright and terms-of-service obligations remain the user's responsibility.
- The project currently provides command-line and batch-file workflows rather than a standalone GUI.

## Release History

### ResearchReader v2.0.0

This release establishes the platform architecture for long-term development:

- Core and AI Pipeline separation
- Unified Article Engine
- Prompt Framework
- AI Quality Engine
- Research Notes and Research Packages
- Workspace and Manifest support
- Backward-compatible CLI workflows

See [RELEASE_NOTES.md](RELEASE_NOTES.md) for the complete release description.
