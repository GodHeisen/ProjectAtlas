"""Research agent that gathers and structures geopolitical research."""

import json
import re
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

    Phase 1b (incremental improvement):
    - Splits retrieved sources into chunks of ``sources_per_call`` to avoid
      overwhelming small local models with too many sources in a single prompt.
    - Extracts from each chunk independently, then merges all structured
      findings and generates a single, coherent summary from the combined
      extraction.
    - Deduplicates near-identical claims before packaging to reduce noise.
    """

    name = "research"

    # Richer research needs more raw material to decompose into atomic,
    # source-cited claims. 20 results (vs. the search service's own default
    # of 10) gives the extraction prompt enough breadth across sources to
    # reach a substantial claim count for well-documented topics.
    _SEARCH_RESULT_LIMIT = 20

    # Number of sources to include in a single LLM extraction call. Smaller
    # chunks keep each prompt below local-model context limits and give each
    # source-group independent LLM attention.
    _SOURCES_PER_CALL = 4

    def __init__(
        self,
        storage: StorageService,
        prompt_service: PromptService,
        search_service: SearchServiceInterface,
        llm_service: LLMService | None = None,
        sources_per_call: int | None = None,
    ) -> None:
        super().__init__()
        self._storage = storage
        self._prompts = prompt_service
        self._search = search_service
        self._llm = llm_service
        self._sources_per_call = (
            sources_per_call if sources_per_call is not None else self._SOURCES_PER_CALL
        )

    def run(self, project_input: ProjectInput, project_dir: Path) -> ResearchPackage:
        """Execute research for a project and write all required output files."""
        topic = self._resolve_topic(project_input)
        self.logger.info("Starting research for topic: %s", topic)

        search_results = self._search.search(topic, max_results=self._SEARCH_RESULT_LIMIT)
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
            extraction = self._extract_in_chunks(project_input, topic, sources)
            return self._package_from_extraction(topic, sources, extraction)
        except (json.JSONDecodeError, LLMError, ValidationError, ValueError) as exc:
            self.logger.warning("Research extraction was unusable: %s", exc)
            return self._incomplete_package(
                topic,
                "Sources were retrieved, but Atlas could not validate a source-cited "
                "structured extraction from them.",
                sources=sources,
            )

    def _extract_in_chunks(
        self,
        project_input: ProjectInput,
        topic: str,
        sources: list[Source],
    ) -> _ResearchExtraction:
        """Extract findings in source-groups (chunks), then merge and summarise.

        Processing sources in small chunks gives each group the LLM's full
        attention rather than having the model spread itself thin across all
        sources in one oversized prompt.
        """
        chunk_size = self._sources_per_call
        chunks = [sources[i : i + chunk_size] for i in range(0, len(sources), chunk_size)]
        self.logger.info(
            "Splitting %d source(s) into %d chunk(s) of up to %d sources each.",
            len(sources),
            len(chunks),
            chunk_size,
        )

        extractions: list[_ResearchExtraction] = []
        for idx, chunk in enumerate(chunks, start=1):
            chunk_ids = [s.id for s in chunk]
            self.logger.info("Extracting chunk %d/%d: sources %s", idx, len(chunks), chunk_ids)
            extraction = self._request_extraction(project_input, topic, chunk)
            extractions.append(extraction)

        merged = self._merge_extractions(extractions)
        # Discard individual chunk summaries; generate a single coherent
        # summary from the combined extraction.
        merged.summary = ""
        merged.summary_source_refs = []
        all_source_ids = {s.id for s in sources}
        merged = self._generate_final_summary(project_input, topic, merged, all_source_ids)
        return merged

    @staticmethod
    def _merge_extractions(extractions: list[_ResearchExtraction]) -> _ResearchExtraction:
        """Concatenate all structured findings across extraction chunks."""
        timeline: list[TimelineEvent] = []
        entities: list[Entity] = []
        relations: list[Relation] = []
        claims: list[_ExtractedClaim] = []
        questions: list[ResearchQuestion] = []

        for ext in extractions:
            timeline.extend(ext.timeline)
            entities.extend(ext.entities)
            relations.extend(ext.relations)
            claims.extend(ext.claims)
            questions.extend(ext.questions)

        return _ResearchExtraction(
            timeline=timeline,
            entities=entities,
            relations=relations,
            claims=claims,
            questions=questions,
        )

    def _generate_final_summary(
        self,
        project_input: ProjectInput,
        topic: str,
        merged: _ResearchExtraction,
        all_source_ids: set[str],
    ) -> _ResearchExtraction:
        """Request a single, coherent summary from the complete merged extraction.

        Discards per-chunk summaries and asks the LLM to produce one
        summary grounded in all extracted findings.
        """
        findings_summary = self._build_findings_digest(merged)
        summary_prompt = (
            f"Based on the extracted research findings below, write a concise, "
            f"neutral documentary summary about: {topic}.\n\n"
            f"User input for context: {project_input.content}\n\n"
            f"Extracted findings:\n{findings_summary}\n\n"
            "Respond with valid JSON only, using this exact shape:\n"
            '{{"summary": "your summary here", "summary_source_refs": ["source-1"]}}\n'
            'Use empty arrays/strings when no sources support a claim.'
        )
        system = (
            "You are a documentary research summarizer. Synthesize the supplied "
            "extracted findings into a factual, neutral summary. Do not add claims "
            "not supported in the findings. Cite source IDs that the findings reference."
        )
        response = self._llm.complete(system, summary_prompt)
        try:
            parsed = json.loads(self._strip_json_fence(response))
            text = (parsed.get("summary") or "").strip()
            refs = [
                ref for ref in parsed.get("summary_source_refs") or []
                if ref in all_source_ids
            ]
            if text and refs:
                merged.summary = text
                merged.summary_source_refs = refs
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self.logger.warning("Final summary generation failed, proceeding without one: %s", exc)
        return merged

    @staticmethod
    def _build_findings_digest(extraction: _ResearchExtraction) -> str:
        """Build a compact text digest of all findings for the summary prompt."""
        parts: list[str] = []
        if extraction.claims:
            claims_text = "\n".join(
                f"  - [{', '.join(c.source_refs)}] {c.text}" for c in extraction.claims
            )
            parts.append(f"Claims ({len(extraction.claims)}):\n{claims_text}")
        if extraction.timeline:
            events_text = "\n".join(
                f"  - [{', '.join(e.sources)}] {e.date}: {e.title} — {e.description}"
                for e in extraction.timeline
            )
            parts.append(f"Timeline events ({len(extraction.timeline)}):\n{events_text}")
        if extraction.entities:
            entities_text = "\n".join(
                f"  - [{', '.join(e.source_refs)}] {e.name} ({e.entity_type}): {e.description}"
                for e in extraction.entities
            )
            parts.append(f"Entities ({len(extraction.entities)}):\n{entities_text}")
        if extraction.relations:
            relations_text = "\n".join(
                f"  - [{', '.join(r.source_refs)}] {r.source} -> {r.target} ({r.relation_type})"
                for r in extraction.relations
            )
            parts.append(f"Relations ({len(extraction.relations)}):\n{relations_text}")
        return "\n\n".join(parts) or "No structured findings were extracted."

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
        claims = self._deduplicate_claims(
            [
                Claim(
                    id=f"claim-{uuid4().hex[:8]}",
                    text=claim.text,
                    context=claim.context,
                    source_refs=self._valid_refs(claim.source_refs, valid_source_ids),
                )
                for claim in extraction.claims
                if self._valid_refs(claim.source_refs, valid_source_ids)
            ]
        )

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
    def _deduplicate_claims(claims: list[Claim]) -> list[Claim]:
        """Remove near-identical claims by normalising text and comparing.

        Two claims are considered duplicates when their normalised text
        (lowercased, stripped, whitespace-collapsed) is identical OR one
        is a substring of the other.
        """
        if not claims:
            return []

        def _normalise(text: str) -> str:
            return re.sub(r"\s+", " ", text.lower().strip())

        deduped: list[Claim] = []
        seen: set[str] = set()

        for claim in claims:
            norm = _normalise(claim.text)
            if not norm or norm in seen:
                continue
            # Check substring containment against already-accepted claims
            if any(norm in _normalise(c.text) or _normalise(c.text) in norm for c in deduped):
                continue
            seen.add(norm)
            deduped.append(claim)

        return deduped

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