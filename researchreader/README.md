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

Show resolved global settings:

```bash
python run.py --settings
```

The test command checks configuration, API connectivity, configured model availability, and first-token latency.

API keys are read from environment variables:

- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `NVIDIA_API_KEY`
- `OPENROUTER_API_KEY`

## Configuration Center

Global settings live in:

```text
researchreader/config/settings.toml
```

The Configuration Center resolves:

- default provider
- model override, if configured
- target language
- concurrency, retry count, and timeout
- output directory
- cache and logging defaults

Translation pipelines resolve provider details from the Provider Catalog and environment variables. Callers no longer need to pass API keys or base URLs through `PipelineContext.runtime_options`.

Provider definitions live in the Provider Catalog:

```text
researchreader/config/providers/
```

ResearchReader automatically discovers every `*.toml` file in that directory. Each file describes exactly one provider.

Enabled providers appear in:

```bash
python run.py --models
python run.py --test
```

Disabled providers appear in `--models` as disabled, but are skipped by `--test`.

## Enabling or disabling a provider

Open the provider preset file and change:

```toml
enabled = true
```

or:

```toml
enabled = false
```

## Adding a custom provider

Add a custom OpenAI-compatible provider by adding another provider table:

```toml
id = "my-company"
display_name = "My Company LLM"
description = "Internal OpenAI-compatible company gateway."
provider_type = "custom"
country = "Custom"
website = "https://llm.example.com"
kind = "openai-compatible"
base_url = "https://llm.example.com/v1"
api_key_env = "MY_COMPANY_API_KEY"
default_model = "company-chat"
enabled = true
```

Save it as:

```text
researchreader/config/providers/my-company.toml
```

No Python code is required.

## Adding a company/private provider

Use `provider_type = "custom"` for private providers. Keep the file local if it contains private URLs or internal naming.

## Contributing a provider preset

Community presets should:

- Add one TOML file under `researchreader/config/providers/`.
- Use `provider_type = "official"` for public model providers or `provider_type = "gateway"` for gateway/proxy projects.
- Set `enabled = false` by default unless it is one of the core built-in providers.
- Avoid secrets and user-specific URLs.
- Use `kind = "openai-compatible"` when the provider implements the OpenAI-compatible API.
