"""OpenAI LLM service wrapper."""

from openai import OpenAI

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, LLMError
from app.core.logger import get_logger

logger = get_logger(__name__)


class LLMService:
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
