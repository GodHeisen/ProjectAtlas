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


class ScriptWriterAgent(BaseAgent):
    """Write documentary scripts from structured research packages.

    Rules:
    - Consumes only immutable, fact-checked research
    - Never copies transcripts
    - Never paraphrases another creator
    - Enforces six-section documentary structure
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

    def _build_script(
        self,
        package: VerifiedResearchPackage,
    ) -> DocumentaryScript:
        """Assemble a script with all required sections."""
        sections: list[ScriptSectionContent] = []
        for section in DocumentaryScript(title=package.topic).section_order():
            sections.append(
                ScriptSectionContent(
                    section=section,
                    title=SECTION_TITLES[section],
                    content=self._section_placeholder(section, package),
                )
            )

        return DocumentaryScript(
            title=package.topic,
            sections=sections,
            tone="professional documentary",
            notes=[
                "Phase 1 scaffold: section structure enforced, prose generation deferred.",
                "Script must not copy transcripts or paraphrase other creators.",
            ],
        )

    def _section_placeholder(
        self,
        section: ScriptSection,
        package: VerifiedResearchPackage,
    ) -> str:
        """Return scaffold content for a script section."""
        if self._llm and self._llm.is_configured():
            system = self._prompts.load("script")
            user = (
                f"Topic: {package.topic}\n"
                f"Section: {SECTION_TITLES[section]}\n"
                f"Summary: {package.summary[:500]}\n"
                f"Fact-checked claims: {len(package.claims)}\n"
                "Write scaffold outline only. Do not fabricate facts."
            )
            return self._llm.complete(system, user)

        return (
            f"[{SECTION_TITLES[section]} — content pending]\n\n"
            f"This section will be populated from verified research for: {package.topic}. "
            f"Only structured research data will be used. No transcript copying."
        )

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
