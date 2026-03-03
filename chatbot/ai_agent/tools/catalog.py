"""Catalog & discovery tools – experiences, routes, establishments, availability.

ERP controllers: experience_controller, route_controller,
establishment_controller, availability_controller.

Covers user stories: BOT-US-001, 002, 003, 004, 005, 007, 014, 015, 052.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import RunContext

from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.ai_agent.models import (
    ERP_BASE_PATH,
    AvailabilityResponse,
    Establishment,
    Experience,
    Route,
)
from chatbot.ai_agent.tools.erp_utils import extract_erp_data

logger = logging.getLogger(__name__)

ERP_TIMEOUT_SECONDS = 15.0


# ------------------------------------------------------------------
# Experiences
# ------------------------------------------------------------------


async def list_experiences(
    ctx: RunContext[AgentDeps],
    page: int = 1,
    page_size: int = 20,
    package_mode: str | None = None,
    search: str | None = None,
    date: str | None = None,
) -> list[Experience]:
    """List bookable experiences from the ERP catalog.

    The ERP returns the canonical, filterable catalog.
    Only experiences with status 'ONLINE' and company 'cheese' are fetched.

    Args:
        ctx: Agent run context with dependencies.
        page: Page number for pagination.
        page_size: Maximum experiences to fetch (default 20).
        package_mode: Filter by "Both", "Public", or "Package".
        search: Keyword for searching in title and description.
        date: Availability date (YYYY-MM-DD).
    """
    logger.debug(
        "[list_experiences] page=%s page_size=%s package_mode=%s search=%s date=%s",
        page,
        page_size,
        package_mode,
        search,
        date,
    )
    payload: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "status": "ONLINE",
        "company": "cheese",
    }

    if package_mode:
        payload["package_mode"] = package_mode
    if search:
        payload["search"] = search
    if date:
        payload["date"] = date

    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.experience_controller.list_experiences",
        json=payload,
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data: list[dict[str, Any]] = extract_erp_data(response.json())

    return [
        Experience.model_validate(item)
        for item in data
        if item.get("status") == "ONLINE"
    ]


async def get_experience_detail(
    ctx: RunContext[AgentDeps],
    experience_id: str,
) -> dict[str, Any]:
    """Get full details and policies of a single experience.

    Args:
        ctx: Agent run context with dependencies.
        experience_id: ERP id/name of the experience.
    """
    logger.debug("[get_experience_detail] experience_id=%s", experience_id)
    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.experience_controller.get_experience_detail",
        json={"experience_id": experience_id},
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return extract_erp_data(response.json())


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


async def list_routes(
    ctx: RunContext[AgentDeps],
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> list[Route]:
    """List available themed routes with their composition.

    Args:
        ctx: Agent run context with dependencies.
        page: Page number for pagination.
        page_size: Maximum routes to fetch (default 20).
        search: Keyword for searching in route names and descriptions.
    """
    logger.debug(
        "[list_routes] page=%s page_size=%s search=%s", page, page_size, search
    )
    payload: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
        "status": "ONLINE",
    }
    if search:
        payload["search"] = search

    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.route_controller.list_routes",
        json=payload,
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data: list[dict[str, Any]] = extract_erp_data(response.json())
    return [Route.model_validate(item) for item in data]


async def get_route_detail(
    ctx: RunContext[AgentDeps],
    route_id: str,
) -> dict[str, Any]:
    """Get full route detail: composition, rules, conditions.

    Args:
        ctx: Agent run context with dependencies.
        route_id: ERP id/name of the route.
    """
    logger.debug("[get_route_detail] route_id=%s", route_id)
    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.route_controller.get_route_detail",
        json={"route_id": route_id},
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return extract_erp_data(response.json())


# ------------------------------------------------------------------
# Establishments
# ------------------------------------------------------------------


async def list_establishments(
    ctx: RunContext[AgentDeps],
    page: int = 1,
    page_size: int = 20,
) -> list[Establishment]:
    """List establishments with pagination.

    Args:
        ctx: Agent run context with dependencies.
        page: Page number (1-based).
        page_size: Items per page.
    """
    logger.debug("[list_establishments] page=%s page_size=%s", page, page_size)
    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.establishment_controller.list_establishments",
        json={"page": page, "page_size": page_size},
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data: list[dict[str, Any]] = extract_erp_data(response.json())
    return [Establishment.model_validate(item) for item in data]


async def get_establishment_details(
    ctx: RunContext[AgentDeps],
    establishment_id: str,
) -> dict[str, Any]:
    """Get full establishment profile.

    Args:
        ctx: Agent run context with dependencies.
        establishment_id: ERP id of the establishment.
    """
    logger.debug("[get_establishment_details] establishment_id=%s", establishment_id)
    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.establishment_controller.get_establishment_details",
        json={"company_id": establishment_id},
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return extract_erp_data(response.json())


# ------------------------------------------------------------------
# Availability
# ------------------------------------------------------------------


async def get_availability(
    ctx: RunContext[AgentDeps],
    experience_id: str,
    date: str,
) -> AvailabilityResponse:
    """Check real-time availability for an experience on a given date.

    Args:
        ctx: Agent run context with dependencies.
        experience_id: ERP id of the experience.
        date: ISO-format date string (YYYY-MM-DD).
    """
    logger.debug(
        "[get_availability] experience_id=%s date=%s",
        experience_id,
        date,
    )
    payload: dict[str, Any] = {
        "experience_id": experience_id,
        "date": date,
    }

    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.availability_controller.get_availability",
        json=payload,
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return AvailabilityResponse.model_validate(extract_erp_data(response.json()))


async def get_route_availability(
    ctx: RunContext[AgentDeps],
    route_id: str,
    date: str,
    party_size: int,
) -> dict[str, Any]:
    """Get aggregated availability for a route on a given date.

    Args:
        ctx: Agent run context with dependencies.
        route_id: ERP id/name of the route.
        date: ISO-format date string (YYYY-MM-DD).
        party_size: Number of people in the group.
    """
    logger.debug(
        "[get_route_availability] route_id=%s date=%s party_size=%s",
        route_id,
        date,
        party_size,
    )
    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.availability_controller.get_route_availability",
        json={
            "route_id": route_id,
            "date": date,
            "party_size": party_size,
        },
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return extract_erp_data(response.json())
