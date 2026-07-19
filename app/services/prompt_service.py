"""Prompt loading and template rendering service."""

from pathlib import Path

from app.core.constants import PROMPTS_DIR
from app.core.exceptions import AtlasError


class PromptService:
    """Load centralized prompt files from app/prompts/."""

    def __init__(self, prompts_dir: Path | None = None) -> None:
        self._prompts_dir = prompts_dir or PROMPTS_DIR

    def load(self, name: str) -> str:
        """Load a prompt file by name (without extension)."""
        path = self._prompts_dir / f"{name}.md"
        if not path.exists():
            raise AtlasError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8")

    def render(self, name: str, **variables: str) -> str:
        """Load a prompt and substitute {variable} placeholders safely."""
        template = self.load(name)
        try:
            return template.format(**variables)
        except KeyError as exc:
            raise AtlasError(f"Missing prompt variable for '{name}': {exc}") from exc
