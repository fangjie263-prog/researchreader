# ResearchReader

一个用于采集、解析、翻译和阅读财经新闻及出版物的个人开源工具。

许可证： [MIT](LICENSE)

MIT 许可证只覆盖本仓库中的原创代码。第三方依赖、下载的 EPUB/PDF、抓取的网站内容、API 服务和模型输出，仍然受各自的许可证、版权和服务条款约束。

## 当前功能

### HKEJ 新闻抓取与 HTML 阅读

`run_hkej.bat` 可以抓取信报即时新闻，并将最新 TXT/JSON 转换为 HTML。

```powershell
run_hkej.bat
```

也可以手动转换：

```powershell
python hkej_to_html.py path\to\hkej_news.txt
python hkej_to_html.py path\to\hkej_news.json
```

### WSJ / EPUB 批处理

将 EPUB 放入 `books\`，运行：

```powershell
run_wsj.bat
```

程序会按文件名逐本处理，并为每本书生成独立目录：

```text
output\书名\
├── daily.html
├── extracted_articles.md
├── translation_progress.json
└── images\
```

支持：

- 解析 EPUB 文章和图片
- 按文章标题、作者和副标题合并被拆开的文章片段
- 去除重复段落和重复图片
- 生成 HTML 和 Markdown
- 使用 OpenAI 兼容接口翻译文章
- 保存翻译进度并支持中断后继续
- API 失败自动重试
- 损坏 EPUB 写入 `ERROR.txt` 并继续处理其他文件

可选配置：

```bat
set WSJ_API_DELAY=5
set WSJ_API_RETRIES=3
set WSJ_ANALYZE=1
set WSJ_TRANSLATE=1
run_wsj.bat
```

默认只提取原文并生成 HTML/Markdown，不自动翻译或逐篇分析；上面两个变量需要显式设置为 `1` 才会启用对应功能。推荐先运行 `research_digest.py` 做主题筛选。

### PDF 批处理

将文本型 PDF 放入 `books\`，运行：

```powershell
run_pdf.bat
```

程序会扫描所有 `.pdf` 文件，按文件名逐个处理，并生成：

```text
output\PDF文件名\
├── daily.html
└── extracted_articles.md
```

PDF 使用 PyMuPDF 的文字块提取方式，尽量保持标题、段落块和双栏阅读顺序，同时保留可复制文本。当前不支持扫描图片型 PDF 的 OCR。

单个 PDF 也可以直接转换：

```powershell
python pdf_reader.py path\to\document.pdf
python pdf_reader.py path\to\document.pdf --output output\document.html
```

### AI 接口

AI 功能使用 OpenAI 兼容的 Chat Completions 接口。推荐使用交互式设置：

```powershell
python ai_setup.py setup
python ai_setup.py test
python ai_setup.py test --timeout 15 --top 5
python ai_setup.py test --model DeepSeek-V4-Flash
python ai_setup.py test --provider hcnsec
```

`setup` 会安全地隐藏输入 API Key，并保存到本机的 `ai_settings.json`；需要显示粘贴时可使用 `python ai_setup.py setup --visible-key`。`test` 会请求可用模型列表，逐个进行小请求测速，并推荐当前响应最快的可用模型。默认单模型超时 30 秒、测试前 10 个模型；单个模型失败或超时不会中断整个测试。每次测试都会生成 `benchmark.json`，供后续 GUI 或其他工具读取。

也支持环境变量配置：

```text
AI_API_KEY=your-api-key
AI_BASE_URL=https://your-provider.example/v1
AI_MODEL=your-model
AI_ENDPOINT=/chat/completions
```

AI 可用于财经摘要、投资相关性评分、匹配关注主题和文章翻译。API 密钥不要提交到 Git 仓库。

### 关注主题

用中文添加主题，AI 会自动生成中文关键词、英文关键词和相关概念：

```powershell
python topic_manager.py add "人工智能" "半导体"
python topic_manager.py list
python topic_manager.py remove "半导体"
```

主题保存到本机的 `topics.json`，不会提交到 Git。WSJ 的 AI 摘要会把这些主题和扩展词作为分析上下文，并返回 `matched_topics`。

### 重点筛选后再给阅读建议

不会先把所有文章完整翻译成中英文。运行：

```powershell
python research_digest.py
```

它会先免费扫描 `output\` 下已有的 MD/HTML，用关注主题和中英文扩展词做本地筛选；只有命中的文章才发送标题和短摘录给 AI。AI 只对推荐阅读的文章输出优先级、阅读理由，以及简短的中英文摘要，不输出整篇双语内容。

结果保存为：

```text
output\reading_recommendations.md
output\reading_recommendations.html
```

也可以运行 `run_digest.bat`。每次最多筛选 30 篇候选文章，可通过代码中的上限调整。

## 安装依赖

建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 自动化测试

运行全部测试：

```powershell
python -m unittest discover -s tests -v
```

测试覆盖当前核心逻辑，包括：

- EPUB 文章合并和段落去重规则
- PDF 段落去重、跨页合并和 HTML 转义
- PDF Markdown 输出格式
- HKEJ TXT/JSON 解析和 HTML 生成
- AI 环境变量配置和启用条件

## 目录说明

```text
wsj_reader.py       EPUB 解析、文章合并和 HTML/Markdown 输出
wsj_queue.py        EPUB 批处理、翻译、重试和进度保存
pdf_reader.py       单个 PDF 的文字块解析和 HTML 输出
pdf_queue.py        PDF 批处理和 per-file 输出
hkej_to_html.py     HKEJ TXT/JSON 到 HTML
ai_service.py       OpenAI 兼容接口客户端
ai_setup.py         API 设置、Key 测试和模型测速
topic_manager.py    关注主题及中英文关键词扩展
research_digest.py  重点主题筛选和阅读建议
tests\              自动化测试
books\              输入 EPUB/PDF
output\             生成结果
```

## 已知限制

- 扫描型 PDF 需要另行接入 OCR。
- 复杂杂志版式不保证完全还原；当前优先保证文字可复制和段落可读。
- HKEJ、WSJ、Economist 等内容的版权和网站服务条款不由本项目许可证覆盖。
- 本项目目前是命令行和批处理工具，没有独立图形界面。
