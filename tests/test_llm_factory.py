"""Tests for LLMFactory provider selection."""

import pytest

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.services.llm_factory import LLMFactory
from app.services.llm_service import LLMService
from app.services.ollama_llm_service import OllamaLLMService


def build_settings(**overrides) -> Settings:
    return Settings(
        OPENAI_API_KEY=overrides.get("openai_api_key", ""),
        LLM_PROVIDER=overrides.get("llm_provider", "openai"),
        OLLAMA_HOST=overrides.get("ollama_host", "http://localhost:11434"),
        OLLAMA_MODEL=overrides.get("ollama_model", "qwen2.5:3b"),
    )


def test_factory_defaults_to_openai() -> None:
    service = LLMFactory.create(build_settings())
    assert isinstance(service, LLMService)


def test_factory_returns_openai_explicitly() -> None:
    service = LLMFactory.create(build_settings(llm_provider="openai"))
    assert isinstance(service, LLMService)


def test_factory_returns_ollama_when_configured() -> None:
    service = LLMFactory.create(build_settings(llm_provider="ollama"))
    assert isinstance(service, OllamaLLMService)


def test_factory_provider_selection_is_case_insensitive() -> None:
    service = LLMFactory.create(build_settings(llm_provider="OLLAMA"))
    assert isinstance(service, OllamaLLMService)


def test_factory_raises_on_unknown_provider() -> None:
    with pytest.raises(ConfigurationError):
        LLMFactory.create(build_settings(llm_provider="anthropic"))


def test_factory_result_satisfies_llm_service_interface() -> None:
    from app.services.llm_service import LLMServiceInterface

    openai_service = LLMFactory.create(build_settings(llm_provider="openai"))
    ollama_service = LLMFactory.create(build_settings(llm_provider="ollama"))
    assert isinstance(openai_service, LLMServiceInterface)
    assert isinstance(ollama_service, LLMServiceInterface)
