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
- **No fabricated research** — search stub returns empty results until a real provider is wired

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
| `ResearchAgent` | Phase 1 implemented | Produce source-cited research artifacts or an explicit incomplete package |
| `FactCheckAgent` | Phase 1 scaffold | Tag claims with verification status |
| `ScriptWriterAgent` | Phase 1 scaffold | Write six-section documentary scripts |
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
│   ├── services/        # LLM, search, storage, prompt, export
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
- [x] FactCheckAgent and ScriptWriterAgent skeletons
- [ ] Wire real web search provider
- [ ] LLM-powered research synthesis from verified primary sources
- [ ] Full documentary prose generation

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
