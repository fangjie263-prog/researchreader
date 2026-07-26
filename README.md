\# ResearchReader



A personal AI-powered news reader and scraper.



\## Overview



ResearchReader is a personal project for collecting, reading and processing financial news with AI.



\## Current Status



\### Completed



\- Git repository initialized

\- Connected to GitHub

\- PowerShell HKEJ scraper

\- Git ignore configured



\### In Progress



\- Python HKEJ scraper



\## Roadmap



\- Improve Python scraper

\- Add Wall Street Journal support

\- Add Financial Times support

\- AI summarization

\- Daily news digest



\## Run



PowerShell



```powershell

powershell -ExecutionPolicy Bypass -File .\\hkej\_scraper.ps1

```



Python



```bash

python work\\hkej\_scraper.py

```

HKEJ HTML

`run_hkej.bat` 抓取完成后会自动把最近生成的 HKEJ TXT/JSON 转换为 `output\\hkejYYYYMMDDHHMMSS.html`，例如 `hkej20260719065341.html`。

也可以手动转换：

```bash
python hkej_to_html.py path\\to\\hkej_news.txt
python hkej_to_html.py path\\to\\hkej_news.json
```

WSJ EPUB 队列

`run_wsj.bat` 现在会按文件名顺序逐本处理 `books\\*.epub`。每本书单独输出到 `output\\书名\\`，翻译进度保存在该目录的 `translation_progress.json`；程序中断后重新运行会跳过已经完成的文章。

默认每次 API 调用间隔 3 秒，失败时自动重试。可以在运行前设置：

```bat
set WSJ_API_DELAY=5
set WSJ_API_RETRIES=3
run_wsj.bat
```

原始 EPUB 不会被修改。损坏的 EPUB 会记录到对应输出目录的 `ERROR.txt`，并继续处理下一本。

PDF to HTML

文本型 PDF 可直接批量转换为 HTML 和 Markdown。程序默认扫描 `books\\*.pdf`，按文件名顺序逐个处理，每个 PDF 输出到 `output\\文件名\\`，生成 `daily.html` 和 `extracted_articles.md`：

```powershell
run_pdf.bat
```

也可以单独运行 `python pdf_reader.py path\\to\\document.pdf`。PDF 依赖已加入 `requirements.txt`。目前扫描件（没有文本层的 PDF）需要 OCR，程序会明确提示而不会生成空 HTML。

