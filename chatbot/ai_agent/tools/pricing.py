"""Tools for pricing and cancellation policy queries.

Controller: pricing_controller
"""

from __future__ import annotations

import logging

import httpx
from pydantic_ai import ModelRetry, RunContext

from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.ai_agent.models import ERP_BASE_PATH, CancellationImpact
from chatbot.ai_agent.tools.erp_utils import extract_erp_data, extract_erp_error

logger = logging.getLogger(__name__)

ERP_TIMEOUT_SECONDS = 15.0


async def get_cancellation_impact(
    ctx: RunContext[AgentDeps],
    reservation_id: str,
) -> CancellationImpact | str:
    """Check whether a reservation can be cancelled and what the financial impact would be.

    Always call this tool BEFORE attempting to cancel an individual reservation.
    Use the result to:
    - Inform the customer if cancellation is not allowed and why.
    - Show the penalty and refund amount when cancellation is allowed, and ask
      for explicit confirmation before proceeding with the cancellation.

    Args:
        ctx: Agent run context with dependencies.
        reservation_id: The ERP ticket ID to evaluate (e.g. "TKT-2026-03-00067").
    """
    logger.info(
        "[get_cancellation_impact] reservation_id=%s",
        reservation_id,
    )
    try:
        response = await ctx.deps.erp_client.post(
            f"{ERP_BASE_PATH}.pricing_controller.get_cancellation_impact",
            json={"reservation_id": reservation_id},
            timeout=ERP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        error_msg = extract_erp_error(exc.response.json())
        logger.warning(
            "[get_cancellation_impact] HTTP %s — %s",
            exc.response.status_code,
            error_msg,
        )
        raise ModelRetry(f"ERP returned an error: {error_msg}") from exc
    except httpx.RequestError as exc:
        logger.exception("[get_cancellation_impact] network error")
        raise ModelRetry(f"Network error contacting ERP: {exc}") from exc

    data = extract_erp_data(response.json())
    if not isinstance(data, dict):
        raise ModelRetry(
            "Unexpected response format from ERP cancellation impact endpoint."
        )

    return CancellationImpact.model_validate(data)
