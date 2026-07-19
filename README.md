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

