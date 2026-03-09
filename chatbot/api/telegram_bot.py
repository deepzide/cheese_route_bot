"""Telegram chatbot entry point using the Ruta del Queso AI agent.

The Telegram chat_id is used as the user identifier in both the DB
(stored in the ``phone`` column) and the ERP (via ``telegram_id`` in AgentDeps).

Run with:
    uv run python scripts/run_telegram_bot.py
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from chatbot.ai_agent import get_cheese_agent
from chatbot.ai_agent.context import webhook_context_manager
from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.api.utils import message_handler, telegram_commands
from chatbot.api.utils.telegram_commands import (
    cmd_get_availability,
    cmd_get_establishment_details,
    cmd_get_experience_detail,
    cmd_get_route_availability,
    cmd_get_route_detail,
    cmd_list_establishments,
    cmd_list_experiences,
    cmd_list_routes,
    cmd_resolve_or_create_contact,
    cmd_update_contact,
    cmd_upsert_lead,
)
from chatbot.core.config import config
from chatbot.core.logging_conf import init_logging
from chatbot.db.services import services
from chatbot.erp.client import build_erp_client
from chatbot.messaging.telegram_notifier import notify_error
from chatbot.messaging.whatsapp import WhatsAppClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ERP client — created in post_init, closed in post_shutdown
# ---------------------------------------------------------------------------
erp_client: httpx.AsyncClient | None = None

# Stub WhatsApp client (not used in Telegram, but AgentDeps requires it)
_noop_whatsapp = WhatsAppClient()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _typing_loop(bot, chat_id: int) -> None:
    """Send 'typing' chat action every 4 s until the task is cancelled."""
    while True:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(4)


def _extract_tools_used(result) -> list[str]:
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    tools: list[str] = []
    for msg in result.all_messages():
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    tools.append(part.tool_name)
    return tools


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message on /start."""
    if not update.message:
        return
    user = update.effective_user
    await update.message.reply_text(
        f"¡Hola{', ' + user.first_name if user else ''}! 🧀\n"
        "Soy el asistente de *Ruta del Queso*. ¿En qué te puedo ayudar hoy?",
        parse_mode="Markdown",
    )


async def _handle_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/restart clears the conversation history."""
    if not update.message or not update.effective_chat:
        return
    chat_id = str(update.effective_chat.id)
    await services.reset_chat(chat_id)
    await update.message.reply_text("Chat reiniciado. ¿En qué te puedo ayudar?")
    logger.info("'/restart' requested by telegram_id=%s", chat_id)


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process an incoming text message through the AI agent."""
    if not update.message or not update.message.text or not update.effective_chat:
        return

    chat_id_int: int = update.effective_chat.id
    chat_id: str = str(chat_id_int)
    incoming_msg: str = update.message.text

    logger.info("=" * 80)
    logger.info("telegram_id=%s: %s", chat_id, incoming_msg)

    # Start typing indicator loop in background
    typing_task = asyncio.create_task(_typing_loop(context.bot, chat_id_int))

    try:
        await message_handler.save_user_msg(chat_id, incoming_msg)

        assert erp_client is not None, "ERP client not initialized"
        deps = AgentDeps(
            erp_client=erp_client,
            db_services=services,
            whatsapp_client=_noop_whatsapp,
            webhook_context=webhook_context_manager,
            user_phone="",
            telegram_id=chat_id,
        )

        agent = get_cheese_agent()
        history = await services.get_pydantic_ai_history(chat_id, hours=24)
        result = await agent.run(incoming_msg, deps=deps, message_history=history)

        ai_response: str = result.output
        tools_used = _extract_tools_used(result)

        logger.info("Agent response for telegram_id=%s: %s", chat_id, ai_response[:120])
        logger.debug("Tools used: %s", tools_used)

        await message_handler.save_assistant_msg(chat_id, ai_response, tools_used)
        await update.message.reply_text(ai_response)

    except Exception as exc:
        logger.exception("Error processing Telegram message for %s: %s", chat_id, exc)
        await notify_error(
            exc,
            context=f"telegram_bot._handle_message | chat_id={chat_id} | msg={incoming_msg[:80]}",
        )
        await update.message.reply_text(
            "Ocurrió un error al procesar tu mensaje. "
            "Por favor inténtalo de nuevo o escribe /restart para reiniciar el chat."
        )
    finally:
        typing_task.cancel()


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------


async def _post_init(application: Application) -> None:
    """Connect to DB and create ERP client on startup."""
    global erp_client
    init_logging()
    logger.info("🤖 Telegram bot starting up")
    await services.database.connect()
    erp_client = build_erp_client()
    telegram_commands.init(erp_client)
    logger.info("✅ DB connected and ERP client ready")


async def _post_shutdown(application: Application) -> None:
    """Disconnect DB and close ERP client on shutdown."""
    global erp_client
    try:
        await services.database.disconnect()
        logger.info("✅ DB disconnected")
    except Exception as exc:
        logger.error("Error disconnecting DB: %s", exc)

    if erp_client:
        try:
            await erp_client.aclose()
            logger.info("✅ ERP client closed")
        except Exception as exc:
            logger.error("Error closing ERP client: %s", exc)


def build_application() -> Application:
    """Build and return the configured PTB Application."""
    if not config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured in .env")

    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("restart", _handle_restart))

    # Direct tool commands — bypass AI agent
    app.add_handler(CommandHandler("list_experiences", cmd_list_experiences))
    app.add_handler(CommandHandler("get_experience_detail", cmd_get_experience_detail))
    app.add_handler(CommandHandler("list_routes", cmd_list_routes))
    app.add_handler(CommandHandler("get_route_detail", cmd_get_route_detail))
    app.add_handler(CommandHandler("list_establishments", cmd_list_establishments))
    app.add_handler(
        CommandHandler("get_establishment_details", cmd_get_establishment_details)
    )
    app.add_handler(CommandHandler("get_availability", cmd_get_availability))
    app.add_handler(
        CommandHandler("get_route_availability", cmd_get_route_availability)
    )
    app.add_handler(
        CommandHandler("resolve_or_create_contact", cmd_resolve_or_create_contact)
    )
    app.add_handler(CommandHandler("update_contact", cmd_update_contact))
    app.add_handler(CommandHandler("upsert_lead", cmd_upsert_lead))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))

    return app
