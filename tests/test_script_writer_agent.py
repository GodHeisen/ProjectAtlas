"""Behaviour tests for the Phase 1 ScriptWriterAgent."""

from app.agents.script_writer_agent import SECTION_TITLES, ScriptWriterAgent
from app.core.config import Settings
from app.core.enums import ClaimStatus, ScriptSection
from app.models.claims import Claim, VerifiedClaim
from app.models.research import VerifiedResearchPackage
from app.services.prompt_service import PromptService
from app.services.storage_service import StorageService


class FixedLLMService:
    """Deterministic LLM replacement that echoes the requested section title."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def is_configured(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        assert "Verified research package" in system_prompt
        return f"Generated narration prose grounded in the supplied research."


def build_settings(tmp_path) -> Settings:
    return Settings(
        DATA_DIR=tmp_path / "data",
        PROJECTS_DIR=tmp_path / "data" / "projects",
        CACHE_DIR=tmp_path / "data" / "cache",
        KNOWLEDGE_DIR=tmp_path / "data" / "knowledge",
    )


def build_verified_package() -> VerifiedResearchPackage:
    claim = Claim(id="claim-1", text="Example State announced new measures.", source_refs=["source-1"])
    verified_claim = VerifiedClaim(
        claim=claim,
        status=ClaimStatus.REPORTED,
        confidence=0.6,
        source_references=("source-1",),
        rationale="Reported by the supplied source.",
    )
    return VerifiedResearchPackage(
        topic="Example Crisis",
        summary="Example State announced new measures amid rising tension.",
        summary_source_refs=("source-1",),
        claims=(verified_claim,),
    )


def test_script_with_no_research_writes_honest_placeholder(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = StorageService(settings)
    project_dir = storage.create_project_dir("empty-topic")
    agent = ScriptWriterAgent(storage, PromptService())

    empty_package = VerifiedResearchPackage(topic="Empty Topic")
    script = agent.run(empty_package, project_dir)

    for section in script.sections:
        assert "content pending" in section.content
    assert "No source-backed research" in script.notes[0]


def test_script_with_no_llm_writes_honest_placeholder(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = StorageService(settings)
    project_dir = storage.create_project_dir("no-llm-topic")
    agent = ScriptWriterAgent(storage, PromptService())  # no llm_service supplied

    script = agent.run(build_verified_package(), project_dir)

    for section in script.sections:
        assert "no LLM is configured" in section.content


def test_script_with_llm_generates_prose_per_section(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = StorageService(settings)
    project_dir = storage.create_project_dir("full-topic")
    llm = FixedLLMService()
    agent = ScriptWriterAgent(storage, PromptService(), llm_service=llm)  # type: ignore[arg-type]

    script = agent.run(build_verified_package(), project_dir)

    assert len(llm.calls) == len(SECTION_TITLES)
    for section in script.sections:
        assert section.content == "Generated narration prose grounded in the supplied research."
        assert section.word_count_target is not None

    script_markdown = (project_dir / "script" / "documentary_script.md").read_text(
        encoding="utf-8"
    )
    assert "# Example Crisis" in script_markdown
    assert "## Hook" in script_markdown
    assert "confirmed 0" in script_markdown.lower() or "reported" in script_markdown.lower()


def test_script_section_titles_cover_all_sections() -> None:
    assert set(SECTION_TITLES.keys()) == set(ScriptSection)
