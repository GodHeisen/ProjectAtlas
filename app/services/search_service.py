"""Search service interface and implementations."""

from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

from app.core.exceptions import SearchError
from app.core.logger import get_logger

logger = get_logger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_WIKIPEDIA_USER_AGENT = (
    "ProjectAtlas/0.1 (documentary research tool; "
    "https://github.com/) requests-python"
)


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

    Kept for tests and offline/dry-run use. Never fabricates data.
    """

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        logger.warning(
            "NoOpSearchService is active. Query '%s' returned 0 results.",
            query,
        )
        return []


class WebSearchService(SearchServiceInterface):
    """Live web search with pluggable providers.

    Provider resolution order (first match wins):
    1. explicit ``provider`` constructor argument
    2. ``SEARCH_PROVIDER`` setting, when it is not ``"auto"``
    3. Tavily, when ``TAVILY_API_KEY`` is configured
    4. SerpAPI, when ``SERPAPI_API_KEY`` is configured
    5. Wikipedia's official search JSON API — the default when no keys are
       configured. It requires no API key and, unlike scraping a general
       search engine, is a documented, stable endpoint that doesn't block
       or CAPTCHA ordinary traffic.

    ``duckduckgo`` remains available as an explicit opt-in
    (``SEARCH_PROVIDER=duckduckgo``) for general web results with no key,
    but DuckDuckGo's HTML search page is not an official API and can change
    layout or rate-limit without notice. Because of that, the DuckDuckGo
    path logs detailed request/response diagnostics, saves the raw HTML it
    received to ``duckduckgo_debug.html`` for inspection, and automatically
    falls back to the Wikipedia API if it cannot parse a usable result —
    so a DuckDuckGo breakage never silently returns zero sources.

    Never fabricates results — genuinely unexpected failures raise
    ``SearchError`` rather than returning invented data.
    """

    _TAVILY_URL = "https://api.tavily.com/search"
    _SERPAPI_URL = "https://serpapi.com/search.json"
    _DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
    _WIKIPEDIA_URL = "https://en.wikipedia.org/w/api.php"

    def __init__(
        self,
        settings=None,
        provider: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        from app.core.config import get_settings

        self._settings = settings or get_settings()
        self._timeout = timeout
        self._provider = (provider or self._resolve_provider()).lower()

    def _resolve_provider(self) -> str:
        """Pick a provider based on explicit config, falling back sensibly."""
        configured = (getattr(self._settings, "search_provider", "") or "auto").lower()
        if configured != "auto":
            return configured
        if getattr(self._settings, "tavily_api_key", ""):
            return "tavily"
        if getattr(self._settings, "serpapi_api_key", ""):
            return "serpapi"
        # Wikipedia is the safe, key-free default: a documented JSON API
        # rather than a scraped page that can break without notice.
        return "wikipedia"

    @property
    def provider(self) -> str:
        """The active search provider name."""
        return self._provider

    def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        """Execute a search query against the resolved provider."""
        query = query.strip()
        if not query:
            return []

        try:
            if self._provider == "tavily":
                results = self._search_tavily(query, max_results)
            elif self._provider == "serpapi":
                results = self._search_serpapi(query, max_results)
            elif self._provider == "duckduckgo":
                results = self._search_duckduckgo(query, max_results)
            elif self._provider == "wikipedia":
                results = self._search_wikipedia(query, max_results)
            else:
                raise SearchError(f"Unknown search provider: {self._provider}")
        except SearchError:
            raise
        except requests.RequestException as exc:
            logger.error("Search request failed for provider '%s': %s", self._provider, exc)
            raise SearchError(f"Search request failed ({self._provider}): {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - convert any parser failure explicitly
            logger.error("Unexpected search failure for provider '%s': %s", self._provider, exc)
            raise SearchError(f"Unexpected search failure ({self._provider}): {exc}") from exc

        logger.info(
            "Search provider '%s' returned %d result(s) for query '%s'",
            self._provider,
            len(results),
            query,
        )
        return results

    # ---- providers -----------------------------------------------------

    def _search_tavily(self, query: str, max_results: int) -> list[SearchResult]:
        """Query the Tavily search API (requires TAVILY_API_KEY)."""
        api_key = getattr(self._settings, "tavily_api_key", "")
        if not api_key:
            raise SearchError("TAVILY_API_KEY is not set.")

        response = requests.post(
            self._TAVILY_URL,
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()

        results: list[SearchResult] = []
        for item in payload.get("results", [])[:max_results]:
            url = item.get("url", "") or ""
            results.append(
                SearchResult(
                    title=item.get("title") or url or "Untitled",
                    url=url,
                    snippet=(item.get("content") or "").strip(),
                    source=self._domain(url),
                )
            )
        return results

    def _search_serpapi(self, query: str, max_results: int) -> list[SearchResult]:
        """Query SerpAPI's Google search endpoint (requires SERPAPI_API_KEY)."""
        api_key = getattr(self._settings, "serpapi_api_key", "")
        if not api_key:
            raise SearchError("SERPAPI_API_KEY is not set.")

        response = requests.get(
            self._SERPAPI_URL,
            params={
                "engine": "google",
                "q": query,
                "num": max_results,
                "api_key": api_key,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()

        results: list[SearchResult] = []
        for item in payload.get("organic_results", [])[:max_results]:
            url = item.get("link", "") or ""
            results.append(
                SearchResult(
                    title=item.get("title") or url or "Untitled",
                    url=url,
                    snippet=(item.get("snippet") or "").strip(),
                    source=item.get("source") or self._domain(url),
                )
            )
        return results

    def _search_duckduckgo(self, query: str, max_results: int) -> list[SearchResult]:
        """Scrape the key-free DuckDuckGo HTML results page, with diagnostics.

        Logs the outgoing request, the response status/size, the number of
        result elements matched, and saves the raw HTML to
        ``duckduckgo_debug.html`` so parser breakage is easy to diagnose.
        Falls back to the Wikipedia JSON API automatically if the page
        can't be parsed into usable results.
        """
        params = {"q": query}
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        logger.info("DuckDuckGo request: GET %s params=%s", self._DUCKDUCKGO_URL, params)
        try:
            response = requests.get(
                self._DUCKDUCKGO_URL,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            logger.error("DuckDuckGo request failed before a response was received: %s", exc)
            return self._duckduckgo_fallback(query, max_results, reason=str(exc))

        logger.info(
            "DuckDuckGo response: status=%d size=%d bytes final_url=%s",
            response.status_code,
            len(response.content),
            response.url,
        )
        self._save_duckduckgo_debug_html(response.text)

        if response.status_code != 200:
            logger.error("DuckDuckGo returned a non-200 status: %d", response.status_code)
            return self._duckduckgo_fallback(
                query, max_results, reason=f"HTTP {response.status_code}"
            )

        soup = BeautifulSoup(response.text, "lxml")
        # "#links .result" matches DuckDuckGo's current static-HTML markup;
        # "div.result" is kept as a defensive fallback selector.
        result_elements = soup.select("#links .result") or soup.select("div.result")
        logger.info(
            "DuckDuckGo parsed %d result element(s) from the response HTML",
            len(result_elements),
        )

        if not result_elements:
            logger.error(
                "DuckDuckGo returned HTTP 200 but no result elements matched known "
                "selectors ('#links .result', 'div.result') — the page layout likely "
                "changed or DuckDuckGo served a block/CAPTCHA page. Inspect "
                "duckduckgo_debug.html for the raw response."
            )
            return self._duckduckgo_fallback(query, max_results, reason="no result elements parsed")

        results: list[SearchResult] = []
        for result in result_elements:
            link = (
                result.select_one("a.result__a")
                or result.select_one("a.result__url")
                or result.select_one("a[href]")
            )
            if not link or not link.get("href"):
                continue
            url_value = self._clean_duckduckgo_url(link["href"])
            if not url_value:
                continue
            snippet_el = (
                result.select_one("a.result__snippet")
                or result.select_one("div.result__snippet")
                or result.select_one(".result__snippet")
            )
            results.append(
                SearchResult(
                    title=link.get_text(strip=True) or url_value,
                    url=url_value,
                    snippet=snippet_el.get_text(strip=True) if snippet_el else "",
                    source=self._domain(url_value),
                )
            )
            if len(results) >= max_results:
                break

        if not results:
            logger.error(
                "DuckDuckGo matched %d result element(s) but extracted zero usable "
                "links from them; falling back to Wikipedia.",
                len(result_elements),
            )
            return self._duckduckgo_fallback(query, max_results, reason="no usable links extracted")

        return results

    def _duckduckgo_fallback(self, query: str, max_results: int, reason: str) -> list[SearchResult]:
        """Fall back to the stable Wikipedia JSON API when DuckDuckGo scraping fails."""
        logger.warning(
            "DuckDuckGo scraping failed (%s) for query '%s'; falling back to the "
            "Wikipedia JSON API.",
            reason,
            query,
        )
        return self._search_wikipedia(query, max_results)

    def _search_wikipedia(self, query: str, max_results: int) -> list[SearchResult]:
        """Query Wikipedia's official search API — a stable, key-free JSON fallback.

        Not a general web search engine, so results are limited to Wikipedia
        articles. It is, however, a documented, versioned, official API that
        does not block or CAPTCHA ordinary traffic the way scraping a
        general search engine can, which is why it is Atlas's default when
        no paid provider is configured.
        """
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": max_results,
            "format": "json",
        }
        logger.info("Wikipedia request: GET %s params=%s", self._WIKIPEDIA_URL, params)
        response = requests.get(
            self._WIKIPEDIA_URL,
            params=params,
            headers={"User-Agent": _WIKIPEDIA_USER_AGENT},
            timeout=self._timeout,
        )
        logger.info(
            "Wikipedia response: status=%d size=%d bytes",
            response.status_code,
            len(response.content),
        )
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("query", {}).get("search", [])
        logger.info("Wikipedia parsed %d result(s)", len(hits))

        results: list[SearchResult] = []
        for item in hits[:max_results]:
            title = item.get("title", "") or "Untitled"
            url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=self._strip_html(item.get("snippet", "")),
                    source="Wikipedia",
                )
            )
        return results

    # ---- helpers ---------------------------------------------------------

    def _save_duckduckgo_debug_html(self, html: str) -> None:
        """Persist the raw DuckDuckGo response for offline parser debugging."""
        try:
            debug_dir = getattr(self._settings, "cache_dir", None) or Path.cwd()
            debug_path = Path(debug_dir) / "duckduckgo_debug.html"
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(html, encoding="utf-8")
            logger.info("Saved raw DuckDuckGo HTML to %s (%d bytes)", debug_path, len(html))
        except OSError as exc:
            logger.warning("Could not save DuckDuckGo debug HTML: %s", exc)

    @staticmethod
    def _strip_html(fragment: str) -> str:
        """Strip HTML tags (e.g. Wikipedia's <span class="searchmatch">) from text."""
        if not fragment:
            return ""
        return BeautifulSoup(fragment, "lxml").get_text()

    @staticmethod
    def _clean_duckduckgo_url(href: str) -> str:
        """Resolve DuckDuckGo's redirect links (``//duckduckgo.com/l/?uddg=``) to real URLs."""
        if "uddg=" in href:
            parsed = urlparse(href if href.startswith("http") else f"https:{href}")
            target = parse_qs(parsed.query).get("uddg")
            if target:
                return unquote(target[0])
        return href

    @staticmethod
    def _domain(url: str) -> str | None:
        """Extract a bare domain from a URL for display as the source publisher."""
        if not url:
            return None
        netloc = urlparse(url).netloc
        return netloc.replace("www.", "") or None
