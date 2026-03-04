from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import RunContext

from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.ai_agent.models import (
    ERP_BASE_PATH,
    LeadInfo,
    UpdateContactResult,
)
from chatbot.ai_agent.tools.erp_utils import extract_erp_data
from chatbot.ai_agent.tools.utils import open_or_resume_conversation

logger = logging.getLogger(__name__)

ERP_TIMEOUT_SECONDS = 15.0


# ------------------------------------------------------------------
# 1. Contact (contact_controller) – tools
# ------------------------------------------------------------------


async def update_contact(
    ctx: RunContext[AgentDeps],
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    idempotency_key: str = "optional-key-123",
) -> UpdateContactResult | str:
    """Update/Insert one or more fields of the current contact

    **IMPORTANT – pass only the fields you want to change.**


    Args:
        ctx: Agent run context with dependencies.
        name: New display name (only if it differs from the current one).
        email: New email address (only if it differs from the current one).
        phone: New phone number (use with caution – changes the dedup key).
        idempotency_key: Optional client-generated key to prevent duplicate
            updates on retries.
    """
    logger.debug(
        "[update_contact] contact_id=%s name=%s email=%s phone=%s",
        ctx.deps.contact_id,
        name,
        email,
        phone,
    )
    if not ctx.deps.contact_id:
        raise ValueError("contact_id is required in AgentDeps to update a contact")

    if not any([name, email, phone]):
        return "No fields to update. Provide at least one of name, email, or phone."

    payload: dict[str, Any] = {
        "contact_id": ctx.deps.contact_id,
        "idempotency_key": idempotency_key,
    }
    if name is not None:
        payload["name"] = name
    if email is not None:
        payload["email"] = email
    if phone is not None:
        payload["phone"] = phone

    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.contact_controller.update_contact",
        json=payload,
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data: dict[str, Any] = extract_erp_data(response.json())
    result = UpdateContactResult.model_validate(data)

    # Keep deps in sync with the updated values
    updated_contact = result.contact
    is_real_name = bool(
        updated_contact.name
        and updated_contact.name != updated_contact.phone
        and updated_contact.name != (updated_contact.email or "")
    )
    if is_real_name:
        ctx.deps.user_name = updated_contact.name
    if updated_contact.email:
        ctx.deps.user_email = updated_contact.email
    if updated_contact.phone and ctx.deps.user_phone is None:  # Telegram
        ctx.deps.user_phone = updated_contact.phone

    logger.debug(
        "Contact updated: %s – changed fields: %s",
        ctx.deps.contact_id,
        result.changed_fields,
    )
    return result


# ------------------------------------------------------------------
# 3. Leads (lead_controller)
# ------------------------------------------------------------------


async def upsert_lead(
    ctx: RunContext[AgentDeps],
    interest_type: str = "Experience",
) -> LeadInfo:
    conversation_id = ctx.deps.conversation_id
    """Create or update a CRM lead for the current contact

    Called whenever a user shows commercial intent (asks about prices,
    availability, or booking) without completing a reservation. The ERP
    consolidates leads per contact to avoid duplicates.

    Requires ``contact_id`` and ``conversation_id`` in ``ctx.deps``.
    Call ``open_or_resume_conversation`` first if ``conversation_id`` is not set.

    Args:
        ctx: Agent run context with dependencies.
        interest_type: Category of interest (e.g. "Experience", "Route").
    """
    logger.debug(
        "[upsert_lead] contact_id=%s conversation_id=%s interest_type=%s",
        ctx.deps.contact_id,
        conversation_id,
        interest_type,
    )
    if not ctx.deps.contact_id:
        raise ValueError("contact_id is required in AgentDeps to upsert a lead")
    if not conversation_id:
        conversation = await open_or_resume_conversation(ctx)
        conversation_id = conversation.conversation_id

    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.lead_controller.upsert_lead",
        json={
            "contact_id": ctx.deps.contact_id,
            "conversation_id": conversation_id,
            "interest_type": interest_type,
            "status": "OPEN",
        },
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data: dict[str, Any] = extract_erp_data(response.json())

    lead = LeadInfo.model_validate(data)
    logger.debug("Lead upserted: %s – status=%s", lead.lead_id, lead.status)
    return lead
