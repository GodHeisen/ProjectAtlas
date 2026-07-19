"""Programmatic entry point for Project Atlas."""

from app.core.config import get_settings
from app.core.logger import setup_logging
from app.models.project import ProjectInput
from app.pipelines.atlas_pipeline import AtlasPipeline


def run_project(project_input: ProjectInput, phase: int = 1):
    """Run a documentary project through the Atlas pipeline."""
    settings = get_settings()
    setup_logging(settings.log_level)
    pipeline = AtlasPipeline(settings)
    return pipeline.run(project_input, phase=phase)
