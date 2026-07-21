"""OpenAI LLM service wrapper and the shared LLM service interface."""

from abc import ABC, abstractmethod

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, LLMError
from app.core.logger import get_logger

logger = get_logger(__name__)


class LLMHealthCheck(BaseModel):
    """Result of checking whether an LLM provider is reachable and usable."""

    healthy: bool
    message: str


class LLMServiceInterface(ABC):
    """Abstract interface implemented by every LLM provider (OpenAI, Ollama, ...).

    Agents depend only on this interface, so any provider that implements
    it can be swapped in through dependency injection without touching
    agent logic.
    """

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a completion request and return the assistant's text response."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when this provider has the configuration it needs to run."""

    @abstractmethod
    def health_check(self) -> LLMHealthCheck:
        """Return whether the provider is currently reachable and usable."""


class LLMService(LLMServiceInterface):
    """Thin wrapper around the OpenAI chat completions API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Lazily initialize the OpenAI client."""
        if not self._settings.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and configure your key."
            )
        if self._client is None:
            self._client = OpenAI(api_key=self._settings.openai_api_key)
        return self._client

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion request and return assistant text."""
        try:
            response = self.client.chat.completions.create(
                model=self._settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
        except Exception as exc:
            logger.exception("LLM completion failed")
            raise LLMError(f"LLM request failed: {exc}") from exc

        message = response.choices[0].message.content
        if not message:
            raise LLMError("LLM returned an empty response.")
        return message.strip()

    def is_configured(self) -> bool:
        """Return True when an API key is available."""
        return bool(self._settings.openai_api_key)

    def health_check(self) -> LLMHealthCheck:
        """Check whether the OpenAI provider is usable.

        This intentionally avoids making a network call, so checking health
        never consumes API quota. It verifies the one prerequisite Atlas
        controls locally: that an API key is configured.
        """
        if not self.is_configured():
            return LLMHealthCheck(
                healthy=False,
                message=(
                    "OPENAI_API_KEY is not set. Copy .env.example to .env and "
                    "configure your key."
                ),
            )
        return LLMHealthCheck(
            healthy=True,
            message=f"OpenAI provider configured (model={self._settings.openai_model}).",
        )
