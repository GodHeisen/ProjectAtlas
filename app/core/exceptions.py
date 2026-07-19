"""Custom exceptions for Project Atlas."""


class AtlasError(Exception):
    """Base exception for all Atlas errors."""


class ConfigurationError(AtlasError):
    """Raised when configuration is missing or invalid."""


class AgentError(AtlasError):
    """Raised when an agent fails during execution."""


class StorageError(AtlasError):
    """Raised when file or project storage operations fail."""


class LLMError(AtlasError):
    """Raised when LLM service calls fail."""


class SearchError(AtlasError):
    """Raised when search service operations fail."""
