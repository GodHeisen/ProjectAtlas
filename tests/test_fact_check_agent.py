"""Tests for FactCheckAgent's tolerant parsing of local-model JSON responses."""

from app.agents.fact_check_agent import FactCheckAgent
from app.core.config import Settings
from app.core.enums import ClaimStatus
from app.models.claims import Claim
from app.models.research import ResearchPackage, Source
from app.services.prompt_service import PromptService
from app.services.storage_service import StorageService


class FixedLLMService:
    """Deterministic LLM stub returning a preset response string."""

    def __init__(self, response: str) -> None:
        self._response = response

    def is_configured(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return self._response


def build_settings(tmp_path) -> Settings:
    return Settings(
        DATA_DIR=tmp_path / "data",
        PROJECTS_DIR=tmp_path / "data" / "projects",
        CACHE_DIR=tmp_path / "data" / "cache",
        KNOWLEDGE_DIR=tmp_path / "data" / "knowledge",
    )


def build_package() -> ResearchPackage:
    source = Source(
        id="source-1",
        title="Example",
        url="https://example.com",
        publisher="Example",
        notes="Snippet",
    )
    claim = Claim(id="claim-1", text="Example claim.", source_refs=["source-1"])
    return ResearchPackage(
        topic="Example Topic",
        summary="Summary",
        summary_source_refs=["source-1"],
        sources=[source],
        claims=[claim],
    )


def run_fact_check(tmp_path, response: str, project_slug: str = "example-topic"):
    settings = build_settings(tmp_path)
    storage = StorageService(settings)
    project_dir = storage.create_project_dir(project_slug)
    agent = FactCheckAgent(storage, PromptService(), llm_service=FixedLLMService(response))
    return agent.run(build_package(), project_dir)


def test_accepts_wrapped_decisions_object(tmp_path) -> None:
    """The documented, requested shape: a top-level {"decisions": [...]}."""
    response = (
        '{"decisions": [{"claim_id": "claim-1", "status": "reported", '
        '"confidence": 0.4, "source_refs": ["source-1"], "rationale": "test"}]}'
    )
    verified = run_fact_check(tmp_path, response, "wrapped")
    assert verified.claims[0].status == ClaimStatus.REPORTED
    assert verified.claims[0].confidence == 0.4


def test_accepts_bare_decisions_array(tmp_path) -> None:
    """Regression test for the qwen2.5:3b runtime bug: small local models can
    omit the top-level "decisions" wrapper and return the array directly.
    Atlas should still use it rather than discard an otherwise usable
    response and fall back to conservative defaults.
    """
    response = (
        '[{"claim_id": "claim-1", "status": "confirmed", '
        '"confidence": 0.9, "source_refs": ["source-1"], "rationale": "test"}]'
    )
    verified = run_fact_check(tmp_path, response, "bare-array")
    assert verified.claims[0].status == ClaimStatus.CONFIRMED
    assert verified.claims[0].confidence == 0.9


def test_falls_back_conservatively_on_invalid_json(tmp_path) -> None:
    verified = run_fact_check(tmp_path, "not json at all", "invalid-json")
    # Claim has a valid source ref, so the conservative default is REPORTED,
    # not UNVERIFIED — Atlas never discards a traceable source reference.
    assert verified.claims[0].status == ClaimStatus.REPORTED
    assert verified.claims[0].confidence == 0.25


def test_ignores_decisions_for_unknown_claim_ids(tmp_path) -> None:
    response = (
        '[{"claim_id": "claim-does-not-exist", "status": "confirmed", '
        '"confidence": 0.9, "source_refs": ["source-1"], "rationale": "x"}]'
    )
    verified = run_fact_check(tmp_path, response, "unknown-claim-id")
    assert verified.claims[0].status == ClaimStatus.REPORTED
    assert verified.claims[0].confidence == 0.25
