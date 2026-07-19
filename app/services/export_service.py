"""Export and packaging service for project outputs."""

from pathlib import Path

from app.core.logger import get_logger
from app.models.project import ProjectResult

logger = get_logger(__name__)


class ExportService:
    """Prepare project outputs for downstream publishing workflows.

    Phase 1: directory listing and manifest generation only.
    Full YouTube publishing package export is deferred to PublisherAgent.
    """

    def build_manifest(self, result: ProjectResult) -> dict[str, str | list[str]]:
        """Build a lightweight manifest describing generated artifacts."""
        manifest: dict[str, str | list[str]] = {
            "project_id": result.project_id,
            "slug": result.slug,
            "status": result.status,
            "notes": result.notes,
            "artifacts": [],
        }
        if result.project_dir.exists():
            manifest["artifacts"] = sorted(
                str(path.relative_to(result.project_dir))
                for path in result.project_dir.rglob("*.md")
            )
        return manifest

    def write_manifest(self, result: ProjectResult) -> Path:
        """Write a JSON-serializable manifest as markdown metadata."""
        manifest = self.build_manifest(result)
        lines = [
            "# Project Manifest",
            "",
            f"- **Project ID:** {manifest['project_id']}",
            f"- **Slug:** {manifest['slug']}",
            f"- **Status:** {manifest['status']}",
            "",
            "## Artifacts",
            "",
        ]
        for artifact in manifest.get("artifacts", []):
            lines.append(f"- `{artifact}`")
        if manifest.get("notes"):
            lines.extend(["", "## Notes", ""])
            for note in manifest["notes"]:
                lines.append(f"- {note}")

        manifest_path = result.project_dir / "manifest.md"
        manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info("Wrote project manifest to %s", manifest_path)
        return manifest_path
