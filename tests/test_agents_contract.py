"""Contract tests for agent classes."""

import pytest

from app.agents.base_agent import BaseAgent
from app.agents.fact_check_agent import FactCheckAgent
from app.agents.publisher_agent import PublisherAgent
from app.agents.research_agent import ResearchAgent
from app.agents.script_writer_agent import ScriptWriterAgent
from app.agents.storyboard_agent import StoryboardAgent
from app.agents.visual_director_agent import VisualDirectorAgent
from app.core.constants import RESEARCH_FILES
from app.core.exceptions import AgentError
from app.services.prompt_service import PromptService
from app.services.storage_service import StorageService
from app.core.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        DATA_DIR=tmp_path / "data",
        PROJECTS_DIR=tmp_path / "data" / "projects",
        CACHE_DIR=tmp_path / "data" / "cache",
        KNOWLEDGE_DIR=tmp_path / "data" / "knowledge",
    )


def test_research_agent_is_base_agent(settings) -> None:
    agent = ResearchAgent(
        storage=StorageService(settings),
        prompt_service=PromptService(),
        search_service=__import__("app.services.search_service", fromlist=["NoOpSearchService"]).NoOpSearchService(),
    )
    assert isinstance(agent, BaseAgent)
    assert agent.name == "research"


def test_research_output_file_count() -> None:
    assert len(RESEARCH_FILES) == 7


def test_phase2_agents_raise_not_implemented() -> None:
    for agent_cls in (StoryboardAgent, VisualDirectorAgent, PublisherAgent):
        agent = agent_cls()
        with pytest.raises(AgentError):
            agent.run()


def test_script_writer_section_names() -> None:
    from app.agents.script_writer_agent import SECTION_TITLES
    from app.core.enums import ScriptSection

    assert SECTION_TITLES[ScriptSection.HOOK] == "Hook"
    assert SECTION_TITLES[ScriptSection.CONCLUSION] == "Conclusion"


def test_fact_check_agent_name() -> None:
    agent = FactCheckAgent(
        storage=StorageService(Settings()),
        prompt_service=PromptService(),
    )
    assert agent.name == "fact_check"


def test_script_writer_agent_name() -> None:
    agent = ScriptWriterAgent(
        storage=StorageService(Settings()),
        prompt_service=PromptService(),
    )
    assert agent.name == "script_writer"
