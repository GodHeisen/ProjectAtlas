"""Storyboard agent — Phase 2 placeholder."""

from app.agents.base_agent import BaseAgent
from app.core.exceptions import AgentError


class StoryboardAgent(BaseAgent):
    """Generate visual storyboards from documentary scripts.

    NOT IMPLEMENTED — deferred to Phase 2.
    """

    name = "storyboard"

    def run(self, *args, **kwargs):
        raise AgentError(
            "StoryboardAgent is not implemented. Complete Phase 1 before enabling this agent."
        )
