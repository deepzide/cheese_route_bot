from __future__ import annotations

import json
import logging

from pydantic_ai import Agent, RunContext

from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.ai_agent.instructions import resolve_or_create_contact
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
    update_contact,
    upsert_lead,
)

logger = logging.getLogger(__name__)
ERP_TIMEOUT_SECONDS = 15.0

# ---------------------------------------------------------------------------
# Tool registry
# resolve_or_create_contact is NOT here – it runs as @agent.system_prompt
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
    # Customer / CRM (contact resolution runs as system_prompt instruction)
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

        @_cheese_agent.instructions
        async def resolve_or_create_contact_instruction(
            ctx: RunContext[AgentDeps],
        ) -> str:
            return await resolve_or_create_contact(ctx)

        @_cheese_agent.system_prompt
        async def list_experiences_prompt(
            ctx: RunContext[AgentDeps],
        ) -> str:
            logger.info("[list_experiences_prompt] called")
            exp_list = await list_experiences(ctx)
            return json.dumps([exp.model_dump_json() for exp in exp_list])

        @_cheese_agent.system_prompt
        async def list_routes_prompt(
            ctx: RunContext[AgentDeps],
        ) -> str:
            logger.info("[list_routes_prompt] called")
            route_list = await list_routes(ctx)
            return json.dumps([route.model_dump_json() for route in route_list])

        @_cheese_agent.system_prompt
        async def list_establishments_prompt(
            ctx: RunContext[AgentDeps],
        ) -> str:
            logger.info("[list_establishments_prompt] called")
            establishment_list = await list_establishments(ctx)
            return json.dumps(
                [
                    establishment.model_dump_json()
                    for establishment in establishment_list
                ]
            )

        logger.info("Cheese agent initialized with %d tools", len(AGENT_TOOLS))
    return _cheese_agent
