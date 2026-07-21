"""Script writer agent — produces documentary-quality scripts."""

from pathlib import Path

from app.agents.base_agent import BaseAgent
from app.core.enums import ScriptSection
from app.models.research import VerifiedResearchPackage
from app.models.script import DocumentaryScript, ScriptSectionContent
from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService
from app.services.storage_service import StorageService

SECTION_TITLES = {
    ScriptSection.HOOK: "Hook",
    ScriptSection.BACKGROUND: "Background",
    ScriptSection.CURRENT_SITUATION: "Current Situation",
    ScriptSection.ANALYSIS: "Analysis",
    ScriptSection.POSSIBLE_OUTCOMES: "Possible Outcomes",
    ScriptSection.CONCLUSION: "Conclusion",
}

SECTION_GUIDANCE = {
    ScriptSection.HOOK: (
        "Open with a compelling, factual hook built from the single most striking "
        "confirmed or well-reported development in the research. Create intrigue "
        "without speculation or exaggeration."
    ),
    ScriptSection.BACKGROUND: (
        "Establish the historical and contextual background a viewer needs, drawing "
        "on the timeline and entities in the research so the story makes sense to "
        "someone unfamiliar with it."
    ),
    ScriptSection.CURRENT_SITUATION: (
        "Describe the present state of affairs using the most recent confirmed and "
        "reported claims and timeline events. Stay tightly grounded in what the "
        "research actually establishes."
    ),
    ScriptSection.ANALYSIS: (
        "Analyze the driving forces and implications, explicitly separating "
        "confirmed fact from interpretation. Frame analytical claims as analysis, "
        "not established fact."
    ),
    ScriptSection.POSSIBLE_OUTCOMES: (
        "Explore plausible future scenarios grounded in the entities, relations, and "
        "claims in the research. Frame every scenario explicitly as speculation, "
        "never as prediction of fact."
    ),
    ScriptSection.CONCLUSION: (
        "Deliver a measured closing that ties the narrative together and reflects on "
        "its significance, without introducing any new factual claims."
    ),
}

SECTION_WORD_TARGETS = {
    ScriptSection.HOOK: 100,
    ScriptSection.BACKGROUND: 220,
    ScriptSection.CURRENT_SITUATION: 220,
    ScriptSection.ANALYSIS: 220,
    ScriptSection.POSSIBLE_OUTCOMES: 180,
    ScriptSection.CONCLUSION: 120,
}

_MAX_CLAIMS_IN_CONTEXT = 40


class ScriptWriterAgent(BaseAgent):
    """Write documentary scripts from structured, fact-checked research packages.

    Rules:
    - Consumes only immutable, fact-checked research
    - Never copies transcripts or paraphrases another creator's work
    - Enforces the six-section documentary structure
    - Writes an honest placeholder — never fabricated prose — when the
      research package or LLM configuration is insufficient
    """

    name = "script_writer"

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

    def run(
        self,
        package: VerifiedResearchPackage,
        project_dir: Path,
    ) -> DocumentaryScript:
        """Generate a documentary script and write script/documentary_script.md."""
        self.logger.info("Writing documentary script for: %s", package.topic)

        script = self._build_script(package)
        self._storage.write_script_file(project_dir, self._format_script(script))
        self.logger.info("Documentary script written with %d sections.", len(script.sections))
        return script

    def _build_script(self, package: VerifiedResearchPackage) -> DocumentaryScript:
        """Assemble a script with all required sections."""
        research_context = self._format_research_context(package)
        has_material = self._has_usable_research(package)

        sections: list[ScriptSectionContent] = []
        for section in DocumentaryScript(title=package.topic).section_order():
            word_target = SECTION_WORD_TARGETS[section]
            sections.append(
                ScriptSectionContent(
                    section=section,
                    title=SECTION_TITLES[section],
                    content=self._write_section(
                        section, package, research_context, has_material
                    ),
                    word_count_target=word_target,
                )
            )

        return DocumentaryScript(
            title=package.topic,
            sections=sections,
            tone="professional documentary",
            notes=self._production_notes(package, has_material),
        )

    def _write_section(
        self,
        section: ScriptSection,
        package: VerifiedResearchPackage,
        research_context: str,
        has_material: bool,
    ) -> str:
        """Write full narration prose for one section, or an honest placeholder."""
        if not has_material:
            return (
                f"[{SECTION_TITLES[section]} — content pending] Research for "
                f"\"{package.topic}\" has not yet produced any source-backed findings, "
                "so Atlas has not written narration for this section. Populate the "
                "research and fact-check stages first."
            )

        if not self._llm or not self._llm.is_configured():
            return (
                f"[{SECTION_TITLES[section]} — content pending] Verified research is "
                "available, but no LLM is configured to write narration prose. Set "
                "OPENAI_API_KEY to generate full documentary prose for this section."
            )

        system_prompt = self._prompts.render(
            "script",
            topic=package.topic,
            tone="professional documentary",
            section_title=SECTION_TITLES[section],
            section_guidance=SECTION_GUIDANCE[section],
            word_target=str(SECTION_WORD_TARGETS[section]),
            research_context=research_context,
        )
        user_prompt = (
            "Write the narration prose for this section now, following every rule "
            "above. Return only the prose."
        )
        prose = self._llm.complete(system_prompt, user_prompt)
        return self._strip_fence(prose).strip()

    @staticmethod
    def _has_usable_research(package: VerifiedResearchPackage) -> bool:
        """Return True when there is enough verified material to write prose."""
        return bool(
            package.summary_source_refs
            or package.timeline
            or package.entities
            or package.claims
        )

    @staticmethod
    def _format_research_context(package: VerifiedResearchPackage) -> str:
        """Serialize the verified research package into an LLM-readable brief."""
        lines: list[str] = []

        lines.append(f"Summary: {package.summary or 'Not available.'}")

        if package.timeline:
            lines.append("\nTimeline:")
            for event in package.timeline:
                lines.append(f"- {event.date}: {event.title} — {event.description}")

        if package.entities:
            lines.append("\nEntities:")
            for entity in package.entities:
                lines.append(
                    f"- {entity.name} ({entity.entity_type}): "
                    f"{entity.description or 'no description available'}"
                )

        if package.relations:
            lines.append("\nRelations:")
            for relation in package.relations:
                lines.append(
                    f"- {relation.source} -> {relation.target} ({relation.relation_type}): "
                    f"{relation.description or 'no description available'}"
                )

        if package.claims:
            lines.append("\nFact-checked claims:")
            for verified in package.claims[:_MAX_CLAIMS_IN_CONTEXT]:
                lines.append(
                    f"- [{verified.status.value.upper()}, confidence "
                    f"{verified.confidence:.2f}] {verified.claim.text}"
                    + (f" — {verified.rationale}" if verified.rationale else "")
                )
            if len(package.claims) > _MAX_CLAIMS_IN_CONTEXT:
                lines.append(
                    f"- (+{len(package.claims) - _MAX_CLAIMS_IN_CONTEXT} additional "
                    "fact-checked claims omitted for brevity)"
                )

        if package.questions:
            lines.append("\nOpen research questions (do not treat as fact):")
            for question in package.questions:
                lines.append(f"- {question.question}")

        return "\n".join(lines)

    @staticmethod
    def _production_notes(package: VerifiedResearchPackage, has_material: bool) -> list[str]:
        """Build transparent production notes about how the script was generated."""
        if not has_material:
            return [
                "No source-backed research was available; every section is a "
                "placeholder pending research and fact-checking.",
            ]
        confirmed = sum(1 for c in package.claims if c.status.value == "confirmed")
        reported = sum(1 for c in package.claims if c.status.value == "reported")
        return [
            f"Generated from {len(package.sources)} source(s), {len(package.claims)} "
            f"fact-checked claim(s) ({confirmed} confirmed, {reported} reported).",
            "Script must not copy transcripts or paraphrase other creators.",
        ]

    @staticmethod
    def _strip_fence(response: str) -> str:
        """Strip an accidental Markdown code fence from an otherwise plain response."""
        stripped = response.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            return "\n".join(stripped.splitlines()[1:-1]).strip()
        return stripped

    @staticmethod
    def _format_script(script: DocumentaryScript) -> str:
        lines = [
            f"# {script.title}",
            "",
            f"**Tone:** {script.tone}",
            "",
        ]
        for section in script.sections:
            lines.extend(
                [
                    f"## {section.title}",
                    "",
                    section.content,
                    "",
                ]
            )
        if script.notes:
            lines.extend(["---", "", "**Production Notes:**", ""])
            for note in script.notes:
                lines.append(f"- {note}")
            lines.append("")
        return "\n".join(lines) + "\n"
