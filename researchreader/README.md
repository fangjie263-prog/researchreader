# ResearchReader

ResearchReader is an AI research reading platform under active design and development.

## Provider Manager MVP

Sprint 1 introduces a minimal provider manager for OpenAI-compatible LLM providers.

Supported built-in providers:

- OpenAI
- DeepSeek
- NVIDIA
- OpenRouter

List configured providers:

```bash
python run.py --models
```

Test configured providers:

```bash
python run.py --test
```

The test command checks configuration, API connectivity, configured model availability, and first-token latency.

API keys are read from environment variables:

- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `NVIDIA_API_KEY`
- `OPENROUTER_API_KEY`

Provider defaults live in `researchreader/config/default.toml`.
