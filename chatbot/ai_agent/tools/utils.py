from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import RunContext

from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.ai_agent.models import (
    ERP_BASE_PATH,
    ConversationInfo,
)
from chatbot.ai_agent.tools.erp_utils import extract_erp_data

logger = logging.getLogger(__name__)

ERP_TIMEOUT_SECONDS = 15.0


async def open_or_resume_conversation(
    ctx: RunContext[AgentDeps],
    channel: str = "WhatsApp",
) -> ConversationInfo:
    """Open a new conversation or resume the active one for the current contact.

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
        raise ValueError("contact_id is required in AgentDeps to open a conversation")

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
