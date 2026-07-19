"""Publisher agent — Phase 2 placeholder."""

from app.agents.base_agent import BaseAgent
from app.core.exceptions import AgentError


class PublisherAgent(BaseAgent):
    """Prepare YouTube publishing packages: SEO, thumbnails, shorts, metadata.

    NOT IMPLEMENTED — deferred to Phase 2.
    """

    name = "publisher"

    def run(self, *args, **kwargs):
        raise AgentError(
            "PublisherAgent is not implemented. Complete Phase 1 before enabling this agent."
        )
