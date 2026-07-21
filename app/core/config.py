"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import (
    CACHE_DIR,
    DATA_DIR,
    DEFAULT_LOG_LEVEL,
    DEFAULT_OPENAI_MODEL,
    KNOWLEDGE_DIR,
    PROJECTS_DIR,
    PROJECT_ROOT,
)


class Settings(BaseSettings):
    """Runtime configuration for Project Atlas."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default=DEFAULT_OPENAI_MODEL, alias="OPENAI_MODEL")
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, alias="LOG_LEVEL")

    # LLM provider configuration. LLMFactory resolves LLM_PROVIDER to either
    # the OpenAI-backed LLMService (default, requires OPENAI_API_KEY) or the
    # local OllamaLLMService (requires a running Ollama server, no API key).
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="qwen2.5:3b", alias="OLLAMA_MODEL")
    ollama_temperature: float = Field(default=0.2, alias="OLLAMA_TEMPERATURE")
    ollama_timeout: float = Field(default=600.0, alias="OLLAMA_TIMEOUT")

    # Search provider configuration. WebSearchService resolves a provider at
    # runtime: an explicit SEARCH_PROVIDER wins; otherwise Tavily is used if
    # configured, then SerpAPI, then DuckDuckGo (no key required).
    search_provider: str = Field(default="auto", alias="SEARCH_PROVIDER")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    serpapi_api_key: str = Field(default="", alias="SERPAPI_API_KEY")
    data_dir: Path = Field(default=DATA_DIR, alias="DATA_DIR")
    projects_dir: Path = Field(default=PROJECTS_DIR, alias="PROJECTS_DIR")
    cache_dir: Path = Field(default=CACHE_DIR, alias="CACHE_DIR")
    knowledge_dir: Path = Field(default=KNOWLEDGE_DIR, alias="KNOWLEDGE_DIR")

    def ensure_directories(self) -> None:
        """Create required data directories if they do not exist."""
        for directory in (self.data_dir, self.projects_dir, self.cache_dir, self.knowledge_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    settings = Settings()
    settings.ensure_directories()
    return settings
