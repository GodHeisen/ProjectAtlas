"""Research package models."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.claims import Claim, VerifiedClaim
from app.models.timeline import TimelineEvent


class Entity(BaseModel):
    """A person, organization, nation, or other geopolitical entity."""

    name: str
    entity_type: str
    role: str | None = None
    description: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    """A relationship between two entities."""

    source: str
    target: str
    relation_type: str
    description: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """A reference source used during research."""

    id: str
    title: str
    url: str | None = None
    publisher: str | None = None
    accessed_at: str | None = None
    notes: str | None = None


class ResearchQuestion(BaseModel):
    """An open question requiring further investigation."""

    question: str
    priority: str = "medium"
    rationale: str | None = None


class ResearchPackage(BaseModel):
    """Structured research output consumed by downstream agents."""

    topic: str
    summary: str = ""
    summary_source_refs: list[str] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    questions: list[ResearchQuestion] = Field(default_factory=list)


class VerifiedResearchPackage(BaseModel):
    """Immutable, fact-checked research consumed by downstream agents."""

    model_config = ConfigDict(frozen=True)

    topic: str
    summary: str = ""
    summary_source_refs: tuple[str, ...] = ()
    timeline: tuple[TimelineEvent, ...] = ()
    entities: tuple[Entity, ...] = ()
    relations: tuple[Relation, ...] = ()
    claims: tuple[VerifiedClaim, ...] = ()
    sources: tuple[Source, ...] = ()
    questions: tuple[ResearchQuestion, ...] = ()
