# Configuration Reference

Project Atlas is configured entirely through environment variables, loaded
from `.env` (copy `.env.example` to `.env` to get started) via
`app/core/config.py:Settings`.

## Core

| Variable | Default | Description |
|----------|---------|--------------|
| `LOG_LEVEL` | `INFO` | Python logging level. |
| `DATA_DIR` | `./data` | Root data directory. |
| `PROJECTS_DIR` | `./data/projects` | Per-project output directory. |
| `CACHE_DIR` | `./data/cache` | Cache directory (also used for `duckduckgo_debug.html`). |
| `KNOWLEDGE_DIR` | `./data/knowledge` | Reserved for Phase 3 knowledge base indexing. |

## LLM provider

Atlas selects an LLM implementation through `LLMFactory.create(settings)`
(`app/services/llm_factory.py`), which returns an object implementing
`LLMServiceInterface` (`app/services/llm_service.py`). Agents depend only on
that interface, so `LLM_PROVIDER` is the single switch that changes which
concrete provider is used everywhere in the pipeline.

| Variable | Default | Applies to | Description |
|----------|---------|------------|--------------|
| `LLM_PROVIDER` | `openai` | both | `openai` or `ollama`. Any other value raises `ConfigurationError` at startup. |
| `OPENAI_API_KEY` | *(empty)* | openai | Required when `LLM_PROVIDER=openai`. |
| `OPENAI_MODEL` | `gpt-4o` | openai | Chat completions model name. |
| `OLLAMA_HOST` | `http://localhost:11434` | ollama | Base URL of a running Ollama server's HTTP API. |
| `OLLAMA_MODEL` | `qwen2.5:3b` | ollama | Model tag as shown by `ollama list` / `GET /api/tags`. Must be pulled first. |
| `OLLAMA_TEMPERATURE` | `0.2` | ollama | Sampling temperature passed as `options.temperature`. |
| `OLLAMA_TIMEOUT` | `600` | ollama | Read timeout, in seconds, for each Ollama request. A short, fixed 10s connect timeout is used internally regardless of this value — if Ollama isn't running, Atlas fails fast rather than waiting minutes to find out. |

### OllamaLLMService behavior

- **Transport:** HTTP only, via `requests` against `OLLAMA_HOST`. Never
  invokes the `ollama` CLI (no `subprocess`, no `ollama run`).
- **Endpoints used:** `POST /api/chat` for completions (`stream: false`),
  `GET /api/tags` for health checks and model-availability checks.
- **Connect vs. read timeout:** requests use `timeout=(10, OLLAMA_TIMEOUT)` —
  a short, fixed connect timeout (fail fast if Ollama isn't running) and a
  long, configurable read timeout (CPU inference, especially a cold model
  load, can legitimately take minutes).
- **Cold start vs. warm model:** the first call after Ollama starts (or after
  the model has been idle) pays a one-time cost to load model weights into
  RAM, which is what a first-attempt timeout usually means — not that
  Ollama is unhealthy. Every request sets `keep_alive: "30m"`, so the model
  stays resident across the research → fact-check → script-writer calls
  in one pipeline run instead of reloading each time.
- **Bounded output:** every request sets `options.num_predict` (2048) as a
  ceiling on generated tokens, so a model that racks up repeats/loops
  instead of stopping can't silently turn a ~30s call into a multi-minute
  one.
- **Retries:** transient failures (connection errors, timeouts, non-2xx
  responses) are retried with linear backoff (`1s, 2s, ...`, 2 retries by
  default — 3 attempts total). A `404` (model not found) fails immediately
  without retrying, since retrying can't fix a missing model.
- **Oversized prompts:** any single message (system or user) longer than
  ~6000 characters is truncated (head + tail preserved, middle dropped),
  logging a warning, instead of being sent in full and risking a timeout.
- **Structured output:** `complete_json(system_prompt, user_prompt)` sets
  Ollama's `format: "json"` and parses the result, raising `LLMError` if the
  model didn't return valid JSON. This is in addition to the interface's
  standard `complete()`, which returns plain text.
- **Health check:** `health_check()` returns an `LLMHealthCheck(healthy,
  message)`. It distinguishes three failure modes with an actionable
  message for each:
  - Ollama not reachable at `OLLAMA_HOST` (not installed / not running)
  - Ollama reachable, but `OLLAMA_MODEL` hasn't been pulled
  - Healthy — model is available and ready

### Switching providers

Changing providers requires editing exactly one line in `.env`:

```bash
LLM_PROVIDER=ollama   # or: openai
```

No code changes are required, and no agent (`ResearchAgent`,
`FactCheckAgent`, `ScriptWriterAgent`) or `Phase1Pipeline` call site needs to
change — they all consume `LLMServiceInterface`, not a concrete class.

## Search provider

| Variable | Default | Description |
|----------|---------|--------------|
| `SEARCH_PROVIDER` | `auto` | `auto`, `tavily`, `serpapi`, `wikipedia`, or `duckduckgo`. |
| `TAVILY_API_KEY` | *(empty)* | Enables the Tavily provider. |
| `SERPAPI_API_KEY` | *(empty)* | Enables the SerpAPI provider. |

`auto` resolves to Tavily if `TAVILY_API_KEY` is set, else SerpAPI if
`SERPAPI_API_KEY` is set, else Wikipedia's official search API (no key
required). `duckduckgo` is available as an explicit opt-in and automatically
falls back to Wikipedia if its HTML page can't be parsed. See the main
[README](../README.md#search-configuration) for more detail.
