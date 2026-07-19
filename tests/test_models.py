"""Tests for Pydantic data models."""

from app.core.enums import ClaimStatus, InputType, ScriptSection
from app.models.claims import Claim, TaggedClaim
from app.models.project import ProjectInput
from app.models.research import ResearchPackage
from app.models.script import DocumentaryScript


def test_project_input_topic() -> None:
    inp = ProjectInput(input_type=InputType.TOPIC, content="Test topic")
    assert inp.input_type == InputType.TOPIC
    assert inp.content == "Test topic"


def test_claim_status_values() -> None:
    assert ClaimStatus.CONFIRMED.value == "confirmed"
    assert ClaimStatus.UNVERIFIED.value == "unverified"


def test_research_package_defaults() -> None:
    package = ResearchPackage(topic="Test")
    assert package.topic == "Test"
    assert package.claims == []
    assert package.sources == []


def test_tagged_claim_serialization() -> None:
    claim = Claim(id="c1", text="Sample claim")
    tagged = TaggedClaim(claim=claim, status=ClaimStatus.REPORTED)
    data = tagged.model_dump()
    assert data["status"] == "reported"


def test_script_section_order() -> None:
    script = DocumentaryScript(title="Test")
    order = script.section_order()
    assert order[0] == ScriptSection.HOOK
    assert order[-1] == ScriptSection.CONCLUSION
