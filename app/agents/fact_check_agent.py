"""Fact-check agent that produces immutable verified research packages."""

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.agents.base_agent import BaseAgent
from app.core.enums import ClaimStatus
from app.core.exceptions import LLMError
from app.models.claims import Evidence, VerifiedClaim
from app.models.research import ResearchPackage, Source, VerifiedResearchPackage
from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService
from app.services.storage_service import StorageService


class _FactCheckDecision(BaseModel):
    """LLM decision payload validated before it becomes a verified claim."""

    claim_id: str
    status: ClaimStatus
    confidence: float = Field(ge=0.0, le=1.0)
    source_refs: list[str] = Field(default_factory=list)
    rationale: str = ""


class _FactCheckExtraction(BaseModel):
    """Structured LLM response for the fact-check prompt."""

    decisions: list[_FactCheckDecision] = Field(default_factory=list)


class FactCheckAgent(BaseAgent):
    """Evaluate researched claims without inventing evidence.

    A source reference alone can establish that a claim was reported, but not that it
    is confirmed. When no validated decision is available, the agent conservatively
    emits a reported or unverified claim rather than manufacturing support.
    """

    name = "fact_check"

    def __init__(
        self,
        storage: StorageService,
        prompt_service: PromptService,
        llm_service: LLMService | None = None,
    ) -> None:
        super().__init__()
        self._storage = storage
        self._prompts = prompt_service
        self._llm = llm_service

    def run(self, package: ResearchPackage, project_dir: Path) -> VerifiedResearchPackage:
        """Fact-check a research package and write fact_check.md."""
        self.logger.info("Fact-checking %d claims", len(package.claims))
        decisions = self._request_decisions(package)
        verified = self._build_verified_package(package, decisions)
        self._storage.write_fact_check_file(project_dir, self._format_report(verified))
        self.logger.info("Fact-check report written with %d decisions.", len(verified.claims))
        return verified

    def _request_decisions(self, package: ResearchPackage) -> dict[str, _FactCheckDecision]:
        """Return validated LLM decisions, or an empty mapping when unavailable."""
        if not package.claims or not self._llm or not self._llm.is_configured():
            return {}

        try:
            response = self._llm.complete(
                self._prompts.load("factcheck"),
                self._build_fact_check_input(package),
            )
            extraction = _FactCheckExtraction.model_validate_json(self._strip_json_fence(response))
        except (json.JSONDecodeError, LLMError, ValidationError, ValueError) as exc:
            self.logger.warning("Fact-check extraction was unusable: %s", exc)
            return {}

        known_claim_ids = {claim.id for claim in package.claims}
        return {
            decision.claim_id: decision
            for decision in extraction.decisions
            if decision.claim_id in known_claim_ids
        }

    @staticmethod
    def _build_fact_check_input(package: ResearchPackage) -> str:
        """Serialize only structured research and its source registry for review."""
        claims = [
            {
                "id": claim.id,
                "text": claim.text,
                "context": claim.context,
                "source_refs": claim.source_refs,
            }
            for claim in package.claims
        ]
        sources = [
            {
                "id": source.id,
                "title": source.title,
                "publisher": source.publisher,
                "url": source.url,
                "snippet": source.notes,
            }
            for source in package.sources
        ]
        return (
            "Evaluate only the following structured research.\n\n"
            f"Claims:\n{json.dumps(claims, ensure_ascii=False)}\n\n"
            f"Sources:\n{json.dumps(sources, ensure_ascii=False)}"
        )

    def _build_verified_package(
        self,
        package: ResearchPackage,
        decisions: dict[str, _FactCheckDecision],
    ) -> VerifiedResearchPackage:
        """Combine research and fact-check decisions into an immutable package."""
        source_index = {source.id: source for source in package.sources}
        claims = tuple(
            self._verified_claim(claim, decisions.get(claim.id), source_index)
            for claim in package.claims
        )
        return VerifiedResearchPackage(
            topic=package.topic,
            summary=package.summary,
            summary_source_refs=tuple(package.summary_source_refs),
            timeline=tuple(package.timeline),
            entities=tuple(package.entities),
            relations=tuple(package.relations),
            claims=claims,
            sources=tuple(package.sources),
            questions=tuple(package.questions),
        )

    def _verified_claim(
        self,
        claim,
        decision: _FactCheckDecision | None,
        source_index: dict[str, Source],
    ) -> VerifiedClaim:
        """Create one conservative decision while preserving every source reference."""
        original_refs = tuple(dict.fromkeys(claim.source_refs))
        cited_refs = self._valid_refs(
            decision.source_refs if decision else list(original_refs),
            source_index,
        )

        if not decision:
            status = ClaimStatus.REPORTED if cited_refs else ClaimStatus.UNVERIFIED
            confidence = 0.25 if cited_refs else 0.0
            rationale = (
                "Claim is traceable to retrieved reporting but has not been independently "
                "verified."
                if cited_refs
                else "No source reference is available; the claim cannot be verified."
            )
        elif not cited_refs:
            status = ClaimStatus.UNVERIFIED
            confidence = 0.0
            rationale = (
                "The proposed decision did not cite a supplied source, so Atlas cannot "
                "treat it as evidence."
            )
        else:
            status = decision.status
            confidence = decision.confidence
            rationale = decision.rationale or "Assessment based on the cited source material."

        return VerifiedClaim(
            claim=claim,
            status=status,
            confidence=confidence,
            evidence=tuple(self._evidence_for(source_index[ref]) for ref in cited_refs),
            source_references=original_refs,
            rationale=rationale,
        )

    @staticmethod
    def _valid_refs(refs: list[str], source_index: dict[str, Source]) -> tuple[str, ...]:
        """Keep only unique references that exist in the research source registry."""
        return tuple(dict.fromkeys(ref for ref in refs if ref in source_index))

    @staticmethod
    def _evidence_for(source: Source) -> Evidence:
        """Expose retrieved source material as evidence without rewriting it."""
        return Evidence(
            source_id=source.id,
            title=source.title,
            publisher=source.publisher,
            url=source.url,
            excerpt=source.notes,
        )

    @staticmethod
    def _strip_json_fence(response: str) -> str:
        """Accept JSON fenced by an otherwise compliant LLM response."""
        stripped = response.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            return "\n".join(stripped.splitlines()[1:-1]).strip()
        return stripped

    @staticmethod
    def _format_report(package: VerifiedResearchPackage) -> str:
        """Render a transparent markdown record of all fact-check decisions."""
        lines = ["# Fact Check Report", ""]
        if not package.claims:
            lines.append("_No claims were available for fact-checking._")
            return "\n".join(lines) + "\n"

        for verified in package.claims:
            lines.extend(
                [
                    f"## {verified.claim.id}",
                    f"- **Claim:** {verified.claim.text}",
                    f"- **Status:** `{verified.status.value}`",
                    f"- **Confidence:** {verified.confidence:.2f}",
                    f"- **Original source references:** {', '.join(verified.source_references) or 'None'}",
                    f"- **Rationale:** {verified.rationale or 'N/A'}",
                    "- **Evidence:**",
                ]
            )
            if verified.evidence:
                for evidence in verified.evidence:
                    lines.append(
                        f"  - {evidence.source_id}: {evidence.title} "
                        f"({evidence.publisher or 'publisher unknown'})"
                    )
            else:
                lines.append("  - None")
            lines.append("")
        return "\n".join(lines) + "\n"
