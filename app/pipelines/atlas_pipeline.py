"""Full Atlas pipeline — routes to phase-specific pipelines."""

from app.core.config import Settings
from app.core.logger import get_logger
from app.models.project import ProjectInput, ProjectResult
from app.pipelines.phase1_pipeline import Phase1Pipeline

logger = get_logger(__name__)


class AtlasPipeline:
    """Top-level pipeline entry point for Project Atlas."""

    def __init__(self, settings: Settings | None = None) -> None:
        from app.core.config import get_settings

        self._settings = settings or get_settings()
        self._phase1 = Phase1Pipeline(self._settings)

    def run(self, project_input: ProjectInput, phase: int = 1) -> ProjectResult:
        """Run the requested pipeline phase."""
        if phase == 1:
            return self._phase1.run(project_input)
        raise NotImplementedError(f"Pipeline phase {phase} is not implemented yet.")
