"""Dependency injection container for the AI agent.

Provides all external services the agent needs: ERP client, DB services,
WhatsApp client, and per-conversation webhook context.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from chatbot.ai_agent.context import WebhookContextManager
from chatbot.db.services import Services
from chatbot.messaging.whatsapp import WhatsAppClient


@dataclass
class AgentDeps:
    """Dependencies injected into every agent run via RunContext."""

    erp_client: httpx.AsyncClient
    db_services: Services
    whatsapp_client: WhatsAppClient
    webhook_context: WebhookContextManager
    user_phone: str = ""
    user_name: str | None = None
    user_email: str | None = None
    telegram_id: str | None = None
    contact_id: str | None = None
    conversation_id: str | None = None
