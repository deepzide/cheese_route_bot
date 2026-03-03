"""Customer management tools – contacts, conversations and leads.

ERP controllers: contact_controller, conversation_controller, lead_controller.

Covers user stories: BOT-US-011, 012, 013, 038.

Flow required before creating a lead:
  1. resolve_or_create_contact  -> sets ctx.deps.contact_id
  2. open_or_resume_conversation -> sets ctx.deps.conversation_id
  3. upsert_lead
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import RunContext

from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.ai_agent.models import (
    ERP_BASE_PATH,
    ContactInfo,
    ConversationInfo,
    LeadInfo,
)
from chatbot.ai_agent.tools.erp_utils import extract_erp_data

logger = logging.getLogger(__name__)

ERP_TIMEOUT_SECONDS = 15.0


# ------------------------------------------------------------------
# 1. Contact (contact_controller)
# ------------------------------------------------------------------


async def resolve_or_create_contact(
    ctx: RunContext[AgentDeps],
    phone: str | None = None,
    name: str | None = None,
    email: str | None = None,
) -> ContactInfo:
    """Resolve an existing contact or create a new one by phone number.

    The ERP deduplicates by phone/email so calling this function repeatedly
    with the same phone is idempotent (BOT-US-011).

    If no phone is provided, falls back to ``ctx.deps.user_phone``.

    Args:
        ctx: Agent run context with dependencies.
        phone: WhatsApp / international phone number (e.g. "+598 99 000 001").
        name: Contact display name (optional, used only on creation).
        email: Contact email address (optional).
    """
    logger.debug(
        "[resolve_or_create_contact] phone=%s name=%s email=%s",
        phone,
        name,
        email,
    )
    resolved_phone: str = phone or ctx.deps.user_phone

    payload: dict[str, Any] = {"phone": resolved_phone}
    if name:
        payload["name"] = name
    if email:
        payload["email"] = email

    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.contact_controller.resolve_or_create_contact",
        json=payload,
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data: dict[str, Any] = extract_erp_data(response.json())

    contact = ContactInfo.model_validate(data)
    # Keep deps in sync so subsequent tools can use contact_id directly
    ctx.deps.contact_id = contact.contact_id
    logger.debug("Contact resolved: %s (is_new=%s)", contact.contact_id, contact.is_new)
    return contact


async def update_contact(
    ctx: RunContext[AgentDeps],
    idempotency_key: str = "optional-key-123",
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    """Update allowed fields of the current contact (BOT-US-012).

    Only fields explicitly provided are sent to the ERP; omitted fields are
    left unchanged. The ERP audits every modification and returns the list of
    changed fields plus an audit_event_id for traceability.

    Args:
        ctx: Agent run context with dependencies.
        name: New display name for the contact.
        email: New email address.
        phone: New phone number (use with caution – changes the dedup key).
        idempotency_key: client-generated key to prevent duplicate
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

    logger.debug(
        "Contact updated: %s – changed fields: %s",
        ctx.deps.contact_id,
        data.get("changed_fields"),
    )
    return data


# ------------------------------------------------------------------
# 2. Conversation (conversation_controller)
# ------------------------------------------------------------------


async def open_or_resume_conversation(
    ctx: RunContext[AgentDeps],
    channel: str = "WhatsApp",
) -> ConversationInfo:
    """Open a new conversation or resume the active one for the current contact.

    Must be called after ``resolve_or_create_contact`` and before
    ``upsert_lead``. Stores the resulting conversation_id in
    ``ctx.deps.conversation_id`` for use by subsequent tools.

    Args:
        ctx: Agent run context with dependencies.
        channel: Communication channel (default "WhatsApp").
    """
    logger.debug(
        "[open_or_resume_conversation] contact_id=%s channel=%s",
        ctx.deps.contact_id,
        channel,
    )
    if not ctx.deps.contact_id:
        raise ValueError(
            "contact_id is required in AgentDeps to open a conversation. Use 'resolve_or_create_contact' first"
        )

    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.conversation_controller.open_or_resume_conversation",
        json={
            "contact_id": ctx.deps.contact_id,
            "channel": channel,
            "status": "ACTIVE",
        },
        timeout=ERP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    data: dict[str, Any] = extract_erp_data(response.json())

    conversation = ConversationInfo.model_validate(data)
    ctx.deps.conversation_id = conversation.conversation_id
    logger.debug(
        "Conversation opened: %s (is_new=%s)",
        conversation.conversation_id,
        conversation.is_new,
    )
    return conversation


# ------------------------------------------------------------------
# 3. Leads (lead_controller)
# ------------------------------------------------------------------


async def upsert_lead(
    ctx: RunContext[AgentDeps],
    interest_type: str = "Experience",
) -> LeadInfo:
    """Create or update a CRM lead for the current contact (BOT-US-038).

    Called whenever a user shows commercial intent (asks about prices,
    availability, or booking) without completing a reservation. The ERP
    consolidates leads per contact to avoid duplicates.

    Requires ``contact_id`` and ``conversation_id`` in ``ctx.deps``.
    Call ``resolve_or_create_contact`` and ``open_or_resume_conversation``
    first if they are not set.

    Args:
        ctx: Agent run context with dependencies.
        interest_type: Category of interest (e.g. "Experience", "Route").
    """
    logger.debug(
        "[upsert_lead] contact_id=%s conversation_id=%s interest_type=%s",
        ctx.deps.contact_id,
        ctx.deps.conversation_id,
        interest_type,
    )
    if not ctx.deps.contact_id:
        raise ValueError(
            "contact_id is required in AgentDeps to upsert a lead. Use 'resolve_or_create_contact' first"
        )
    if not ctx.deps.conversation_id:
        raise ValueError(
            "conversation_id is required in AgentDeps to upsert a lead. Use 'open_or_resume_conversation' first"
        )

    response = await ctx.deps.erp_client.post(
        f"{ERP_BASE_PATH}.lead_controller.upsert_lead",
        json={
            "contact_id": ctx.deps.contact_id,
            "conversation_id": ctx.deps.conversation_id,
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
