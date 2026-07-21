"""Tests for WebSearchService provider resolution and response parsing."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.exceptions import SearchError
from app.services.search_service import WebSearchService


def build_settings(**overrides) -> Settings:
    return Settings(
        OPENAI_API_KEY="",
        SEARCH_PROVIDER=overrides.get("search_provider", "auto"),
        TAVILY_API_KEY=overrides.get("tavily_api_key", ""),
        SERPAPI_API_KEY=overrides.get("serpapi_api_key", ""),
    )


def test_provider_defaults_to_wikipedia_with_no_keys() -> None:
    service = WebSearchService(settings=build_settings())
    assert service.provider == "wikipedia"


def test_provider_prefers_tavily_when_key_present() -> None:
    service = WebSearchService(settings=build_settings(tavily_api_key="key"))
    assert service.provider == "tavily"


def test_provider_prefers_serpapi_over_wikipedia() -> None:
    service = WebSearchService(settings=build_settings(serpapi_api_key="key"))
    assert service.provider == "serpapi"


def test_explicit_provider_setting_wins() -> None:
    service = WebSearchService(
        settings=build_settings(tavily_api_key="key", search_provider="duckduckgo")
    )
    assert service.provider == "duckduckgo"


def test_empty_query_returns_no_results_without_network_call() -> None:
    service = WebSearchService(settings=build_settings())
    assert service.search("   ") == []


def test_tavily_search_parses_results() -> None:
    service = WebSearchService(settings=build_settings(tavily_api_key="key"))
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "results": [
            {
                "title": "Example report",
                "url": "https://example.com/report",
                "content": "A detailed report.",
            }
        ]
    }
    fake_response.raise_for_status = MagicMock()

    with patch("app.services.search_service.requests.post", return_value=fake_response) as post:
        results = service.search("example query", max_results=5)

    assert post.called
    assert len(results) == 1
    assert results[0].title == "Example report"
    assert results[0].url == "https://example.com/report"
    assert results[0].source == "example.com"


def test_search_raises_search_error_on_request_failure() -> None:
    import requests

    service = WebSearchService(settings=build_settings(tavily_api_key="key"))
    with patch(
        "app.services.search_service.requests.post",
        side_effect=requests.ConnectionError("boom"),
    ):
        with pytest.raises(SearchError):
            service.search("example query")


def test_wikipedia_search_parses_results() -> None:
    service = WebSearchService(settings=build_settings())
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = b"x" * 100
    fake_response.json.return_value = {
        "query": {
            "search": [
                {
                    "title": "Example Topic",
                    "snippet": "An <span class=\"searchmatch\">example</span> snippet.",
                }
            ]
        }
    }
    fake_response.raise_for_status = MagicMock()

    with patch(
        "app.services.search_service.requests.get", return_value=fake_response
    ) as get:
        results = service.search("example query", max_results=5)

    assert get.called
    assert len(results) == 1
    assert results[0].title == "Example Topic"
    assert results[0].url == "https://en.wikipedia.org/wiki/Example_Topic"
    assert results[0].snippet == "An example snippet."
    assert results[0].source == "Wikipedia"


def test_duckduckgo_parses_html_results_via_get(tmp_path) -> None:
    settings = build_settings(search_provider="duckduckgo")
    settings.cache_dir = tmp_path
    service = WebSearchService(settings=settings)
    html = """
    <div class="result">
      <a class="result__a" href="https://example.com/article">Example Article</a>
      <a class="result__snippet">Snippet text here.</a>
    </div>
    """
    fake_response = MagicMock()
    fake_response.text = html
    fake_response.content = html.encode("utf-8")
    fake_response.status_code = 200
    fake_response.url = "https://html.duckduckgo.com/html/?q=example+query"
    fake_response.raise_for_status = MagicMock()

    with patch(
        "app.services.search_service.requests.get", return_value=fake_response
    ) as get:
        results = service.search("example query", max_results=3)

    assert get.called
    assert len(results) == 1
    assert results[0].url == "https://example.com/article"
    assert results[0].title == "Example Article"
    assert results[0].snippet == "Snippet text here."
    assert (tmp_path / "duckduckgo_debug.html").exists()


def test_duckduckgo_falls_back_to_wikipedia_when_unparseable(tmp_path) -> None:
    settings = build_settings(search_provider="duckduckgo")
    settings.cache_dir = tmp_path
    service = WebSearchService(settings=settings)

    ddg_response = MagicMock()
    ddg_response.text = "<html><body>Unexpected block page</body></html>"
    ddg_response.content = b"Unexpected block page"
    ddg_response.status_code = 200
    ddg_response.url = "https://html.duckduckgo.com/html/?q=example"
    ddg_response.raise_for_status = MagicMock()

    wiki_response = MagicMock()
    wiki_response.status_code = 200
    wiki_response.content = b"x" * 50
    wiki_response.json.return_value = {
        "query": {"search": [{"title": "Fallback Result", "snippet": "Fallback snippet."}]}
    }
    wiki_response.raise_for_status = MagicMock()

    with patch(
        "app.services.search_service.requests.get",
        side_effect=[ddg_response, wiki_response],
    ):
        results = service.search("example", max_results=3)

    assert len(results) == 1
    assert results[0].title == "Fallback Result"
    assert results[0].source == "Wikipedia"
