from __future__ import annotations

import logging

from pydantic_ai import Agent

from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.ai_agent.prompts import SYSTEM_PROMPT

from chatbot.ai_agent.tools.catalog import (
    get_availability,
    get_establishment_details,
    get_experience_detail,
    get_route_availability,
    get_route_detail,
    list_establishments,
    list_experiences,
    list_routes,
)
from chatbot.ai_agent.tools.customer import (
    resolve_or_create_contact,
    update_contact,
    upsert_lead,
)


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool registry (all tools the agent can call)
# ---------------------------------------------------------------------------

AGENT_TOOLS = [
    # Catalog & discovery
    list_experiences,
    get_experience_detail,
    list_routes,
    get_route_detail,
    list_establishments,
    get_establishment_details,
    # Availability
    get_availability,
    get_route_availability,
    # Customer / CRM
    resolve_or_create_contact,
    update_contact,
    upsert_lead,
]


# ---------------------------------------------------------------------------
# Lazy singleton
# ---------------------------------------------------------------------------

_cheese_agent: Agent[AgentDeps, str] | None = None


def get_cheese_agent() -> Agent[AgentDeps, str]:
    """Return the singleton cheese agent, creating it on first call."""
    global _cheese_agent  # noqa: PLW0603
    if _cheese_agent is None:
        _cheese_agent = Agent(
            model="openai:gpt-5",
            system_prompt=SYSTEM_PROMPT,
            deps_type=AgentDeps,
            tools=AGENT_TOOLS,
        )
        logger.info("Cheese agent initialized with %d tools", len(AGENT_TOOLS))
    return _cheese_agent
