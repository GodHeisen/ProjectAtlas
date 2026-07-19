"""Abstract base class for all Atlas agents."""

from abc import ABC, abstractmethod
from typing import Any

from app.core.logger import get_logger


class BaseAgent(ABC):
    """Base class providing shared logging for all agents."""

    name: str = "base"

    def __init__(self) -> None:
        self.logger = get_logger(f"atlas.agent.{self.name}")

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the agent's primary responsibility."""
