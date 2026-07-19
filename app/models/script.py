"""Documentary script models."""

from pydantic import BaseModel, Field

from app.core.enums import ScriptSection


class ScriptSectionContent(BaseModel):
    """Content for a single documentary script section."""

    section: ScriptSection
    title: str
    content: str = ""
    word_count_target: int | None = None


class DocumentaryScript(BaseModel):
    """Full documentary script with enforced section structure."""

    title: str
    sections: list[ScriptSectionContent] = Field(default_factory=list)
    tone: str = "professional documentary"
    notes: list[str] = Field(default_factory=list)

    def section_order(self) -> list[ScriptSection]:
        """Return canonical section order for documentary scripts."""
        return [
            ScriptSection.HOOK,
            ScriptSection.BACKGROUND,
            ScriptSection.CURRENT_SITUATION,
            ScriptSection.ANALYSIS,
            ScriptSection.POSSIBLE_OUTCOMES,
            ScriptSection.CONCLUSION,
        ]
