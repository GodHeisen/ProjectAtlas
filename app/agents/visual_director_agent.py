"""Visual director agent — Phase 2 placeholder."""

from app.agents.base_agent import BaseAgent
from app.core.exceptions import AgentError


class VisualDirectorAgent(BaseAgent):
    """Generate AI image prompts, map instructions, and visual direction.

    NOT IMPLEMENTED — deferred to Phase 2.
    """

    name = "visual_director"

    def run(self, *args, **kwargs):
        raise AgentError(
            "VisualDirectorAgent is not implemented. Complete Phase 1 before enabling this agent."
        )
