# Project Atlas

**AI-powered geopolitical documentary generation platform.**

Project Atlas is a modular software system that researches geopolitical events, verifies information, writes documentary-quality scripts, and eventually produces a complete YouTube publishing package. It is not a script generator, prompt collection, or thin AI wrapper — it is production software built for scale.

---

## Project Overview

Given a single input — a topic, YouTube URL, news article URL, or transcript — Atlas produces a full documentary production package:

| Output | Phase |
|--------|-------|
| Research Report | Phase 1 |
| Timeline | Phase 1 |
| Fact Check | Phase 1 |
| Entities & Relations | Phase 1 |
| Documentary Script | Phase 1 |
| Storyboard | Phase 2 |
| Visual Prompts | Phase 2 |
| Map Instructions | Phase 2 |
| Voice Script | Phase 2 |
| Editing Timeline | Phase 2 |
| Thumbnail Prompt | Phase 2 |
| SEO Package | Phase 2 |
| Shorts Package | Phase 2 |

**Example input:** `Iran threatens UAE after possible US strikes`

---

## Features

- **Modular agent architecture** — each agent has a single responsibility
- **Clean architecture** — models, services, agents, and pipelines are fully separated
- **Centralized prompts** — no hardcoded prompt strings in agent code
- **Typed data models** — Pydantic schemas for all inputs and outputs
- **Markdown-first outputs** — every artifact written as `.md` under `data/projects/`
- **Dependency injection** — services wired through pipeline constructors
- **Live web search** — `WebSearchService` resolves Tavily, SerpAPI, or key-free DuckDuckGo automatically (see [Search Configuration](#search-configuration))
- **Pluggable local or hosted LLM** — `LLMFactory` resolves `LLM_PROVIDER` to OpenAI or a local Ollama server, both behind the same `LLMServiceInterface` (see [LLM Configuration](#llm-configuration))
- **No fabricated research** — every finding is dropped unless it cites a retrieved source; Atlas writes an honest "incomplete" package rather than inventing facts

---

## Architecture

```text
run.py / app/main.py
        │
        ▼
  AtlasPipeline
        │
        ▼
  Phase1Pipeline
   ├── ResearchAgent      → data/projects/{slug}/research/
   ├── FactCheckAgent     → data/projects/{slug}/research/fact_check.md
   └── ScriptWriterAgent  → data/projects/{slug}/script/documentary_script.md
```

### Agents

| Agent | Status | Responsibility |
|-------|--------|----------------|
| `ResearchAgent` | Phase 1 implemented | Produce source-cited research artifacts (via `WebSearchService` + LLM extraction) or an explicit incomplete package |
| `FactCheckAgent` | Phase 1 implemented | Tag every claim with a verification status, confidence, and evidence, conservatively when no decision is available |
| `ScriptWriterAgent` | Phase 1 implemented | Write full six-section documentary narration prose grounded in verified research, or an honest placeholder when research/LLM is unavailable |
| `StoryboardAgent` | Phase 2 placeholder | Visual storyboards |
| `VisualDirectorAgent` | Phase 2 placeholder | AI image prompts, map instructions |
| `PublisherAgent` | Phase 2 placeholder | YouTube publishing package |

---

## Folder Structure

```text
ProjectAtlas/
├── app/
│   ├── agents/          # One class per agent
│   ├── core/            # Config, enums, constants, logging, exceptions
│   ├── models/          # Pydantic data models
│   ├── prompts/         # Centralized prompt files
│   ├── services/        # LLM (OpenAI + Ollama via LLMFactory), search, storage, prompt, export
│   ├── pipelines/       # Phase1Pipeline, AtlasPipeline
│   ├── templates/       # Markdown/Jinja templates (future)
│   ├── utils/           # Shared helpers
│   ├── outputs/         # Runtime staging
│   └── main.py
├── data/
│   ├── projects/        # Per-project output (gitignored)
│   ├── cache/
│   └── knowledge/
├── docs/
├── tests/
├── scripts/
├── .env.example
├── requirements.txt
├── pyproject.toml
├── README.md
└── run.py
```

---

## Installation

Requires **Python 3.13+**.

```bash
cd C:\Projects\ProjectAtlas
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then add your OPENAI_API_KEY
```

### Search Configuration

`WebSearchService` picks a provider automatically, in this order:

1. `SEARCH_PROVIDER` in `.env`, if set to something other than `auto`
2. **Tavily**, if `TAVILY_API_KEY` is set — best result quality for AI research
3. **SerpAPI**, if `SERPAPI_API_KEY` is set — Google search results
4. **Wikipedia**'s official search JSON API — the default when no key is
   configured. Requires no API key and, being a documented API rather than
   a scraped page, doesn't block or change layout without notice.

Set `SEARCH_PROVIDER=duckduckgo` to opt into scraping DuckDuckGo's HTML
results instead, for general web results with no key. Because that page
isn't an official API, Atlas logs the request/response in detail, saves
the raw HTML to `duckduckgo_debug.html` for troubleshooting, and
automatically falls back to Wikipedia if the page can't be parsed — so a
DuckDuckGo layout change never silently returns zero sources.

Atlas therefore produces real, source-cited research with zero search
configuration. Add a `TAVILY_API_KEY` or `SERPAPI_API_KEY` to `.env` for
higher-quality, higher-volume results.

### LLM Configuration

Every agent that needs an LLM (`ResearchAgent`, `FactCheckAgent`,
`ScriptWriterAgent`) depends only on `LLMServiceInterface`
(`app/services/llm_service.py`) — never on a concrete provider. Which
implementation they actually get is decided in one place,
`LLMFactory.create(settings)` (`app/services/llm_factory.py`), based on the
`LLM_PROVIDER` setting:

| `LLM_PROVIDER` | Implementation | Requires |
|----------------|-----------------|----------|
| `openai` (default) | `LLMService` — OpenAI chat completions | `OPENAI_API_KEY` |
| `ollama` | `OllamaLLMService` — local Ollama server, HTTP API only (never the CLI) | Ollama installed and running, model pulled |

Switching providers is a one-line change in `.env` — no code changes, and
no changes to `Phase1Pipeline`'s call sites or any agent.

**To use Ollama:**

```bash
# 1. Install Ollama: https://ollama.com/download
# 2. Pull a small model that runs well on modest CPUs:
ollama pull qwen2.5:3b
# or:
ollama pull llama3.2:3b

# 3. Make sure the server is running (it usually auto-starts):
ollama serve

# 4. In .env:
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_TEMPERATURE=0.2
OLLAMA_TIMEOUT=600
```

`OllamaLLMService` talks to Ollama's REST API (`/api/chat`, `/api/tags`)
exclusively — it never shells out to the `ollama` CLI. Requests use a short,
fixed 10s connect timeout plus a long, configurable read timeout
(`OLLAMA_TIMEOUT`, default 600s) since CPU-only inference — especially a
cold model load — can legitimately take minutes; every request also sets
`keep_alive: "30m"` so the model stays resident across the research →
fact-check → script-writer calls in one run instead of reloading each time,
and `num_predict` caps generated tokens so a looping model can't silently
turn a short call into a multi-minute one. It retries transient failures
with backoff (model-not-found fails immediately instead of retrying, since
retrying won't fix a missing model), truncates any oversized prompt message
instead of risking a timeout, supports Ollama's `format: "json"`
structured-output mode via `complete_json()`, and exposes `health_check()`
to distinguish "Ollama isn't running", "Ollama is running but the model
isn't pulled", and "healthy" — with an actionable message in each case
(e.g. `ollama pull qwen2.5:3b`).

Avoid 7B+ models on modest CPU-only laptops initially; `qwen2.5:3b` and
`llama3.2:3b` are good starting points and can be swapped for a larger
model later purely by changing `OLLAMA_MODEL`.

---

## Usage

```bash
python run.py --topic "Iran threatens UAE after possible US strikes"
python run.py --news-url "https://example.com/article"
python run.py --youtube-url "https://youtube.com/watch?v=..."
python run.py --transcript path/to/transcript.txt
```

Output is written to `data/projects/{slug}/`.

---

## Roadmap

### Phase 1 (current)
- [x] Project structure and clean architecture
- [x] Core models, services, and pipeline wiring
- [x] ResearchAgent source-cited extraction and markdown artifact generation
- [x] FactCheckAgent conservative claim verification
- [x] Wire real web search provider (`WebSearchService`: Tavily / SerpAPI / DuckDuckGo)
- [x] LLM-powered research synthesis from verified primary sources (`LLMFactory`: OpenAI or local Ollama)
- [x] Full documentary prose generation (`ScriptWriterAgent`, via `LLMFactory`)

### Phase 2
- [ ] StoryboardAgent
- [ ] VisualDirectorAgent
- [ ] PublisherAgent (SEO, thumbnail, shorts)

### Phase 3
- [ ] YouTube URL ingestion and transcript extraction
- [ ] News article parsing (newspaper4k)
- [ ] Knowledge base indexing under `data/knowledge/`
- [ ] Multi-project caching and batch runs

---

## Future Plans

- Scale to thousands of concurrent documentary projects
- Source attribution and citation graph
- Human-in-the-loop fact-check review UI
- Export to DaVinci Resolve / Premiere editing timelines
- Automated Shorts clip generation from long-form scripts

---

## License

Private — all rights reserved.
