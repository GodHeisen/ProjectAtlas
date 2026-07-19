"""Claim and fact-check models."""

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ClaimStatus


class Claim(BaseModel):
    """An extracted factual or analytical claim."""

    id: str
    text: str
    context: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class TaggedClaim(BaseModel):
    """A claim annotated with verification status and evidence placeholders."""

    claim: Claim
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    evidence: str | None = Field(
        default=None,
        description="Evidence summary or placeholder for future verification.",
    )
    source_references: list[str] = Field(default_factory=list)
    notes: str | None = None


class FactCheckReport(BaseModel):
    """Complete fact-check output for a research package."""

    tagged_claims: list[TaggedClaim] = Field(default_factory=list)
    summary: str = ""
    open_questions: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """Source material supporting a fact-check decision."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    title: str
    publisher: str | None = None
    url: str | None = None
    excerpt: str | None = None


class VerifiedClaim(BaseModel):
    """An immutable fact-check decision for one researched claim."""

    model_config = ConfigDict(frozen=True)

    claim: Claim
    status: ClaimStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[Evidence, ...] = ()
    source_references: tuple[str, ...] = ()
    rationale: str | None = None

