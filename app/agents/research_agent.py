"""Research agent that gathers and structures geopolitical research."""

import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from app.agents.base_agent import BaseAgent
from app.core.constants import RESEARCH_FILES
from app.core.enums import InputType
from app.core.exceptions import LLMError
from app.models.claims import Claim
from app.models.project import ProjectInput
from app.models.research import Entity, Relation, ResearchPackage, ResearchQuestion, Source
from app.models.timeline import TimelineEvent
from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService
from app.services.search_service import SearchResult, SearchServiceInterface
from app.services.storage_service import StorageService


class _ExtractedClaim(BaseModel):
    """LLM claim payload before Atlas assigns a stable identifier."""

    text: str
    context: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class _ResearchExtraction(BaseModel):
    """Strict, source-cited schema requested from the research prompt."""

    summary: str = ""
    summary_source_refs: list[str] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    claims: list[_ExtractedClaim] = Field(default_factory=list)
    questions: list[ResearchQuestion] = Field(default_factory=list)


class ResearchAgent(BaseAgent):
    """Research topics and produce structured markdown artifacts.

    Phase 1 behavior:
    - Normalizes retrieved search results into stable source references.
    - Uses the injected LLM service only for JSON extraction grounded in those sources.
    - Drops every extracted finding that lacks a valid source reference.
    - Writes the complete research artifact set through StorageService.
    """

    name = "research"

    def __init__(
        self,
        storage: StorageService,
        prompt_service: PromptService,
        search_service: SearchServiceInterface,
        llm_service: LLMService | None = None,
    ) -> None:
        super().__init__()
        self._storage = storage
        self._prompts = prompt_service
        self._search = search_service
        self._llm = llm_service

    def run(self, project_input: ProjectInput, project_dir: Path) -> ResearchPackage:
        """Execute research for a project and write all required output files."""
        topic = self._resolve_topic(project_input)
        self.logger.info("Starting research for topic: %s", topic)

        search_results = self._search.search(topic)
        package = self._build_package(project_input, topic, search_results)

        self._write_outputs(project_dir, package)
        self.logger.info("Research complete. Wrote %d files.", len(RESEARCH_FILES))
        return package

    def _resolve_topic(self, project_input: ProjectInput) -> str:
        """Derive a topic label from the project input."""
        if project_input.title:
            return project_input.title.strip()
        if project_input.input_type == InputType.TOPIC:
            return project_input.content.strip()
        return project_input.content.strip()[:120]

    def _build_package(
        self,
        project_input: ProjectInput,
        topic: str,
        search_results: list[SearchResult],
    ) -> ResearchPackage:
        """Build a source-grounded package or an explicit incomplete package."""
        sources = self._build_sources(search_results)
        if not sources:
            return self._incomplete_package(
                topic,
                "No external sources were retrieved, so Atlas cannot make source-backed "
                "findings for this topic.",
            )

        if not self._llm or not self._llm.is_configured():
            return self._incomplete_package(
                topic,
                "Sources were retrieved, but structured extraction is unavailable because "
                "the LLM service is not configured.",
                sources=sources,
            )

        try:
            extraction = self._request_extraction(project_input, topic, sources)
            return self._package_from_extraction(topic, sources, extraction)
        except (json.JSONDecodeError, LLMError, ValidationError, ValueError) as exc:
            self.logger.warning("Research extraction was unusable: %s", exc)
            return self._incomplete_package(
                topic,
                "Sources were retrieved, but Atlas could not validate a source-cited "
                "structured extraction from them.",
                sources=sources,
            )

    @staticmethod
    def _build_sources(search_results: list[SearchResult]) -> list[Source]:
        """Normalize search results into stable source references."""
        return [
            Source(
                id=f"source-{position}",
                title=result.title,
                url=result.url,
                publisher=result.source,
                notes=result.snippet,
            )
            for position, result in enumerate(search_results, start=1)
        ]

    def _request_extraction(
        self,
        project_input: ProjectInput,
        topic: str,
        sources: list[Source],
    ) -> _ResearchExtraction:
        """Request source-cited JSON extraction through the configured LLM service."""
        source_material = json.dumps(
            [
                {
                    "id": source.id,
                    "title": source.title,
                    "url": source.url,
                    "publisher": source.publisher,
                    "snippet": source.notes,
                }
                for source in sources
            ],
            ensure_ascii=False,
        )
        system = self._prompts.load("research")
        user = self._prompts.render(
            "research",
            topic=topic,
            input_type=project_input.input_type.value,
            content=project_input.content,
            sources=source_material,
        )
        response = self._llm.complete(system, user)
        return _ResearchExtraction.model_validate_json(self._strip_json_fence(response))

    def _package_from_extraction(
        self,
        topic: str,
        sources: list[Source],
        extraction: _ResearchExtraction,
    ) -> ResearchPackage:
        """Accept only findings that cite known retrieved source identifiers."""
        valid_source_ids = {source.id for source in sources}
        summary_source_refs = self._valid_refs(extraction.summary_source_refs, valid_source_ids)
        summary = extraction.summary.strip() if summary_source_refs else ""

        timeline = []
        for event in extraction.timeline:
            event.sources = self._valid_refs(event.sources, valid_source_ids)
            if event.sources:
                timeline.append(event)

        entities = [
            entity
            for entity in extraction.entities
            if self._set_valid_refs(entity, valid_source_ids)
        ]
        relations = [
            relation
            for relation in extraction.relations
            if self._set_valid_refs(relation, valid_source_ids)
        ]
        claims = [
            Claim(
                id=f"claim-{uuid4().hex[:8]}",
                text=claim.text,
                context=claim.context,
                source_refs=self._valid_refs(claim.source_refs, valid_source_ids),
            )
            for claim in extraction.claims
            if self._valid_refs(claim.source_refs, valid_source_ids)
        ]

        if not summary and not any((timeline, entities, relations, claims)):
            return self._incomplete_package(
                topic,
                "Retrieved sources did not yield any validated, source-cited findings.",
                sources=sources,
                questions=extraction.questions,
            )

        return ResearchPackage(
            topic=topic,
            summary=summary or "Atlas extracted source-cited findings; verification remains pending.",
            summary_source_refs=summary_source_refs,
            timeline=timeline,
            entities=entities,
            relations=relations,
            claims=claims,
            sources=sources,
            questions=extraction.questions or self._default_questions(topic),
        )

    @staticmethod
    def _valid_refs(refs: list[str], valid_source_ids: set[str]) -> list[str]:
        """Keep only unique references to supplied sources."""
        return list(dict.fromkeys(ref for ref in refs if ref in valid_source_ids))

    def _set_valid_refs(self, finding: Entity | Relation, valid_source_ids: set[str]) -> bool:
        """Replace a finding's references with valid IDs and report eligibility."""
        finding.source_refs = self._valid_refs(finding.source_refs, valid_source_ids)
        return bool(finding.source_refs)

    def _incomplete_package(
        self,
        topic: str,
        reason: str,
        sources: list[Source] | None = None,
        questions: list[ResearchQuestion] | None = None,
    ) -> ResearchPackage:
        """Return an honest zero-findings package when evidence is unavailable."""
        return ResearchPackage(
            topic=topic,
            summary=f"Research is incomplete. {reason}",
            sources=sources or [],
            questions=questions or self._default_questions(topic),
        )

    @staticmethod
    def _default_questions(topic: str) -> list[ResearchQuestion]:
        """State the minimum next verification step without adding a factual claim."""
        return [
            ResearchQuestion(
                question=(
                    "Which primary or authoritative sources can verify developments "
                    f"related to: {topic}?"
                ),
                priority="high",
                rationale="No validated source-backed finding is available yet.",
            )
        ]

    @staticmethod
    def _strip_json_fence(response: str) -> str:
        """Accept JSON fenced by an otherwise compliant LLM response."""
        stripped = response.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            return "\n".join(stripped.splitlines()[1:-1]).strip()
        return stripped

    def _write_outputs(self, project_dir: Path, package: ResearchPackage) -> None:
        """Write the required research markdown files."""
        writers = {
            "summary.md": self._format_summary(package),
            "timeline.md": self._format_timeline(package),
            "entities.md": self._format_entities(package),
            "relations.md": self._format_relations(package),
            "claims.md": self._format_claims(package),
            "sources.md": self._format_sources(package),
            "questions.md": self._format_questions(package),
        }
        for filename, content in writers.items():
            self._storage.write_research_file(project_dir, filename, content)

    @staticmethod
    def _format_summary(package: ResearchPackage) -> str:
        """Format the source-cited research summary."""
        lines = ["# Summary", "", package.summary]
        if package.summary_source_refs:
            lines.extend(["", f"**Sources:** {', '.join(package.summary_source_refs)}"])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_timeline(package: ResearchPackage) -> str:
        """Format a chronological list of source-cited events."""
        lines = ["# Timeline", ""]
        if not package.timeline:
            lines.append("_No source-backed timeline events are available yet._")
            return "\n".join(lines) + "\n"
        for event in package.timeline:
            lines.extend(
                [
                    f"## {event.date} — {event.title}",
                    "",
                    event.description,
                    f"- **Significance:** {event.significance or 'N/A'}",
                    f"- **Sources:** {', '.join(event.sources)}",
                    "",
                ]
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_entities(package: ResearchPackage) -> str:
        """Format source-cited entities."""
        lines = ["# Entities", ""]
        if not package.entities:
            lines.append("_No source-backed entities are available yet._")
            return "\n".join(lines) + "\n"
        for entity in package.entities:
            lines.extend(
                [
                    f"## {entity.name}",
                    f"- **Type:** {entity.entity_type}",
                    f"- **Role:** {entity.role or 'N/A'}",
                    f"- **Description:** {entity.description or 'N/A'}",
                    f"- **Sources:** {', '.join(entity.source_refs)}",
                    "",
                ]
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_relations(package: ResearchPackage) -> str:
        """Format source-cited relationships."""
        lines = ["# Relations", ""]
        if not package.relations:
            lines.append("_No source-backed relationships are available yet._")
            return "\n".join(lines) + "\n"
        for relation in package.relations:
            lines.extend(
                [
                    f"## {relation.source} → {relation.target}",
                    f"- **Type:** {relation.relation_type}",
                    f"- **Description:** {relation.description or 'N/A'}",
                    f"- **Sources:** {', '.join(relation.source_refs)}",
                    "",
                ]
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_claims(package: ResearchPackage) -> str:
        """Format source-cited claims for the fact-checking stage."""
        lines = ["# Claims", ""]
        if not package.claims:
            lines.append("_No source-backed claims are available yet._")
            return "\n".join(lines) + "\n"
        for claim in package.claims:
            lines.extend(
                [
                    f"## {claim.id}",
                    f"- **Claim:** {claim.text}",
                    f"- **Context:** {claim.context or 'N/A'}",
                    f"- **Sources:** {', '.join(claim.source_refs)}",
                    "",
                ]
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_sources(package: ResearchPackage) -> str:
        """Format the normalized search-source registry."""
        lines = ["# Sources", ""]
        if not package.sources:
            lines.append("_No external sources were retrieved._")
            return "\n".join(lines) + "\n"
        for source in package.sources:
            lines.extend(
                [
                    f"## {source.title}",
                    f"- **ID:** {source.id}",
                    f"- **URL:** {source.url or 'N/A'}",
                    f"- **Publisher:** {source.publisher or 'N/A'}",
                    f"- **Notes:** {source.notes or 'N/A'}",
                    "",
                ]
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_questions(package: ResearchPackage) -> str:
        """Format outstanding research questions."""
        lines = ["# Open Research Questions", ""]
        for question in package.questions:
            lines.extend(
                [
                    f"## {question.question}",
                    f"- **Priority:** {question.priority}",
                    f"- **Rationale:** {question.rationale or 'N/A'}",
                    "",
                ]
            )
        return "\n".join(lines) + "\n"
