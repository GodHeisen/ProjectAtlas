"""Factory that selects an LLMServiceInterface implementation from settings."""

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.core.logger import get_logger
from app.services.llm_service import LLMService, LLMServiceInterface
from app.services.ollama_llm_service import OllamaLLMService

logger = get_logger(__name__)

SUPPORTED_PROVIDERS = ("openai", "ollama")


class LLMFactory:
    """Construct the ``LLMServiceInterface`` implementation for ``LLM_PROVIDER``.

    This is the single place provider selection happens. Everything that
    consumes an LLM service (agents, pipelines) depends only on
    ``LLMServiceInterface``, so adding a new provider means adding one more
    branch here — no other code needs to change.
    """

    @staticmethod
    def create(settings: Settings) -> LLMServiceInterface:
        """Return the configured LLM provider, defaulting to OpenAI."""
        provider = (settings.llm_provider or "openai").strip().lower()

        if provider == "openai":
            logger.info("LLM provider: openai (model=%s)", settings.openai_model)
            return LLMService(settings)

        if provider == "ollama":
            logger.info(
                "LLM provider: ollama (host=%s, model=%s, temperature=%s, timeout=%ss)",
                settings.ollama_host,
                settings.ollama_model,
                settings.ollama_temperature,
                settings.ollama_timeout,
            )
            return OllamaLLMService(settings)

        raise ConfigurationError(
            f"Unknown LLM_PROVIDER '{provider}'. Supported values: "
            f"{', '.join(SUPPORTED_PROVIDERS)}."
        )
