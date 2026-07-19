"""Project file storage service."""

import re
from pathlib import Path

from app.core.config import Settings
from app.core.constants import (
    FACT_CHECK_FILENAME,
    RESEARCH_SUBDIR,
    SCRIPT_FILENAME,
    SCRIPT_SUBDIR,
)
from app.core.exceptions import StorageError


class StorageService:
    """Manage per-project directories and markdown output files."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._settings.ensure_directories()

    @staticmethod
    def slugify(value: str) -> str:
        """Convert arbitrary text into a filesystem-safe slug."""
        slug = value.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_-]+", "-", slug)
        slug = slug.strip("-")
        return slug[:80] or "untitled-project"

    def create_project_dir(self, slug: str) -> Path:
        """Create and return the root directory for a project."""
        project_dir = self._settings.projects_dir / slug
        try:
            project_dir.mkdir(parents=True, exist_ok=True)
            for subdir in (RESEARCH_SUBDIR, SCRIPT_SUBDIR, "storyboard", "visuals", "seo"):
                (project_dir / subdir).mkdir(exist_ok=True)
        except OSError as exc:
            raise StorageError(f"Failed to create project directory: {project_dir}") from exc
        return project_dir

    def write_markdown(self, project_dir: Path, subdir: str, filename: str, content: str) -> Path:
        """Write a markdown file under a project subdirectory."""
        target_dir = project_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
        try:
            target_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise StorageError(f"Failed to write file: {target_path}") from exc
        return target_path

    def write_research_file(self, project_dir: Path, filename: str, content: str) -> Path:
        """Write a file under the research subdirectory."""
        return self.write_markdown(project_dir, RESEARCH_SUBDIR, filename, content)

    def write_script_file(self, project_dir: Path, content: str) -> Path:
        """Write the main documentary script file."""
        return self.write_markdown(project_dir, SCRIPT_SUBDIR, SCRIPT_FILENAME, content)

    def write_fact_check_file(self, project_dir: Path, content: str) -> Path:
        """Write the fact-check report file."""
        return self.write_markdown(project_dir, RESEARCH_SUBDIR, FACT_CHECK_FILENAME, content)
