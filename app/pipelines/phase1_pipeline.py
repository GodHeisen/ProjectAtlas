"""Phase 1 pipeline — Research → FactCheck → ScriptWriter."""

from app.agents.fact_check_agent import FactCheckAgent
from app.agents.research_agent import ResearchAgent
from app.agents.script_writer_agent import ScriptWriterAgent
from app.core.config import Settings
from app.core.logger import get_logger
from app.models.project import ProjectInput, ProjectResult
from app.services.export_service import ExportService
from app.services.llm_service import LLMService
from app.services.prompt_service import PromptService
from app.services.search_service import NoOpSearchService, SearchServiceInterface
from app.services.storage_service import StorageService

logger = get_logger(__name__)


class Phase1Pipeline:
    """Orchestrate Phase 1 agents with dependency injection."""

    def __init__(
        self,
        settings: Settings,
        storage: StorageService | None = None,
        prompt_service: PromptService | None = None,
        search_service: SearchServiceInterface | None = None,
        llm_service: LLMService | None = None,
        export_service: ExportService | None = None,
    ) -> None:
        self._settings = settings
        self._storage = storage or StorageService(settings)
        self._prompts = prompt_service or PromptService()
        self._search = search_service or NoOpSearchService()
        self._llm = llm_service or LLMService(settings)
        self._export = export_service or ExportService()

        self._research = ResearchAgent(
            storage=self._storage,
            prompt_service=self._prompts,
            search_service=self._search,
            llm_service=self._llm,
        )
        self._fact_check = FactCheckAgent(
            storage=self._storage,
            prompt_service=self._prompts,
            llm_service=self._llm,
        )
        self._script_writer = ScriptWriterAgent(
            storage=self._storage,
            prompt_service=self._prompts,
            llm_service=self._llm,
        )

    def run(self, project_input: ProjectInput) -> ProjectResult:
        """Execute the Phase 1 documentary research pipeline."""
        topic_label = project_input.title or project_input.content
        slug = self._storage.slugify(topic_label)
        project_dir = self._storage.create_project_dir(slug)

        logger.info("Running Phase 1 pipeline for project: %s", slug)

        research = self._research.run(project_input, project_dir)
        verified_research = self._fact_check.run(research, project_dir)
        self._script_writer.run(verified_research, project_dir)

        result = ProjectResult(
            slug=slug,
            project_dir=project_dir,
            input=project_input,
            research_dir=project_dir / "research",
            script_dir=project_dir / "script",
            notes=[
                "Phase 1 scaffold complete.",
                "Search service not connected — no external facts fabricated.",
            ],
        )
        self._export.write_manifest(result)
        logger.info("Phase 1 pipeline complete: %s", project_dir)
        return result
