"""Search service interface and stubs."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from app.core.logger import get_logger

logger = get_logger(__name__)


class SearchResult(BaseModel):
    """A single web search result."""

    title: str
    url: str
    snippet: str
    source: str | None = None


class SearchServiceInterface(ABC):
    """Abstract interface for external web search integrations."""

    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Execute a search query and return normalized results."""


class NoOpSearchService(SearchServiceInterface):
    """Placeholder search service that returns no results.

    Used until a real search provider is integrated. Never fabricates data.
    """

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        logger.warning(
            "Search service not configured. Query '%s' returned 0 results. "
            "Integrate WebSearchService before expecting live research.",
            query,
        )
        return []


class WebSearchService(SearchServiceInterface):
    """Future web search implementation hook.

    Implement this class with a real provider (e.g. custom API, SerpAPI, etc.).
    Do not return fabricated results from this stub.
    """

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        raise NotImplementedError(
            "WebSearchService is not implemented. Wire a real provider before use."
        )
