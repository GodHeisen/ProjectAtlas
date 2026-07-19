"""Behaviour tests for the Phase 1 ResearchAgent."""

import json

from app.agents.research_agent import ResearchAgent
from app.core.config import Settings
from app.core.constants import RESEARCH_FILES
from app.core.enums import InputType
from app.models.project import ProjectInput
from app.services.prompt_service import PromptService
from app.services.search_service import NoOpSearchService, SearchResult, SearchServiceInterface
from app.services.storage_service import StorageService


class FixedSearchService(SearchServiceInterface):
    """In-memory search implementation used to verify dependency injection."""

    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        return self._results[:max_results]


class FixedLLMService:
    """Deterministic LLM replacement that returns source-cited JSON."""

    def __init__(self, response: dict) -> None:
        self._response = response

    def is_configured(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        assert "source-1" in user_prompt
        return json.dumps(self._response)


def build_settings(tmp_path) -> Settings:
    """Create isolated project storage for a test."""
    return Settings(
        DATA_DIR=tmp_path / "data",
        PROJECTS_DIR=tmp_path / "data" / "projects",
        CACHE_DIR=tmp_path / "data" / "cache",
        KNOWLEDGE_DIR=tmp_path / "data" / "knowledge",
    )


def test_topic_with_no_search_results_writes_honest_empty_research(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = StorageService(settings)
    project_dir = storage.create_project_dir("test-topic")
    agent = ResearchAgent(storage, PromptService(), NoOpSearchService())

    package = agent.run(
        ProjectInput(input_type=InputType.TOPIC, content="Test topic"),
        project_dir,
    )

    assert package.claims == []
    assert package.entities == []
    assert package.relations == []
    assert package.timeline == []
    assert "Research is incomplete" in package.summary
    assert sorted(path.name for path in (project_dir / "research").glob("*.md")) == sorted(
        RESEARCH_FILES
    )
    assert "[Pending entity extraction]" not in (project_dir / "research" / "entities.md").read_text(
        encoding="utf-8"
    )


def test_source_cited_llm_extraction_populates_research_package(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = StorageService(settings)
    project_dir = storage.create_project_dir("test-topic")
    search = FixedSearchService(
        [
            SearchResult(
                title="Example report",
                url="https://example.com/report",
                snippet="A report describes an event involving Example State.",
                source="Example News",
            )
        ]
    )
    llm = FixedLLMService(
        {
            "summary": "The retrieved report describes an event involving Example State.",
            "summary_source_refs": ["source-1"],
            "timeline": [
                {
                    "date": "2026-01-01",
                    "title": "Reported event",
                    "description": "The report describes an event.",
                    "sources": ["source-1"],
                }
            ],
            "entities": [
                {
                    "name": "Example State",
                    "entity_type": "state",
                    "description": "Named in the retrieved report.",
                    "source_refs": ["source-1"],
                }
            ],
            "relations": [],
            "claims": [
                {
                    "text": "The report describes an event involving Example State.",
                    "context": "Reported by the supplied source.",
                    "source_refs": ["source-1"],
                }
            ],
            "questions": [],
        }
    )
    agent = ResearchAgent(storage, PromptService(), search, llm)  # type: ignore[arg-type]

    package = agent.run(
        ProjectInput(input_type=InputType.TOPIC, content="Example topic"),
        project_dir,
    )

    assert package.summary_source_refs == ["source-1"]
    assert package.timeline[0].sources == ["source-1"]
    assert package.entities[0].source_refs == ["source-1"]
    assert package.claims[0].source_refs == ["source-1"]
    claims_markdown = (project_dir / "research" / "claims.md").read_text(encoding="utf-8")
    assert "source-1" in claims_markdown
