import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from chatbot.api.utils import message_handler
from chatbot.api.utils.message_queue import Message, message_queue
from chatbot.api.utils.session_manager import session_manager
from chatbot.api.utils.webhook_parser import extract_message_content
from chatbot.core.config import config
from chatbot.messaging.whatsapp import whatsapp_manager

logger = logging.getLogger(__name__)
router = APIRouter()
ERROR_STATUS = {"status": "error"}
OK_STATUS = {"status": "ok"}
ERP_ERROR_MSG = "Error de conexion con el ERP. Vuelva a intentarlo mas tarde"
AI_ERROR_MSG = (
    "Explicale al usuario la causa del error y recomiendale "
    "como evitar que vuelva a suceder sin entrar en detalles tecnicos."
    "Dile que si el error persiste puede reiniciar el chat escribiendo '/restart'"
)


@router.get("")
async def verify_webhook(request: Request):
    try:
        mode = request.query_params.get("hub.mode")
        challenge = request.query_params.get("hub.challenge")
        token = request.query_params.get("hub.verify_token")

        verify_token_expected = config.WHATSAPP_VERIFY_TOKEN

        if mode == "subscribe" and token == verify_token_expected:
            logger.info("WEBHOOK VERIFIED for Meta WhatsApp API")
            return PlainTextResponse(str(challenge))
        else:
            logger.warning(
                f"Webhook verification failed - Mode: {mode}, "
                f"Token match: {token == verify_token_expected}"
            )
            raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        logger.error(f"Error in webhook verification: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


async def _process_message(message: Message) -> None:
    """Process a single message from the queue sequentially per user."""
    user_number = message.user_number
    incoming_msg = message.content
    message_id = message.message_id

    if not message_id:
        logger.error("No message_id provided for WhatsApp message")
        return

    await whatsapp_manager.mark_read(message_id)  # marcar como leído
    await whatsapp_manager.send_typing_indicator(message_id)  # escribiendo...

    try:
        if incoming_msg.lower() == "/restart":
            logger.info(f"'/restart' requested by {user_number}")
            #agent.chat_memory.delete_chat(user_number)
            await whatsapp_manager.send_text(
                user_number=user_number, text="Chat reiniciado", message_id=message_id
            )
            return

        logger.info("=" * 100)
        logger.info(f"{user_number}: {incoming_msg}")

        await message_handler.save_user_msg(user_number, incoming_msg)

        """ await message_handler.save_assistant_msg(user_number, ai_response, tools_used)
        await whatsapp_manager.send_text(
            user_number=user_number, text=ai_response, message_id=message_id
        ) """

    finally:
        session_manager.touch_user(user_number)
        await session_manager.cleanup_inactive()


@router.post("")
async def whatsapp_reply(request: Request, background_tasks: BackgroundTasks):
    logger.info("Received WhatsApp message webhook")
    try:
        webhook_data = await request.json()
    except Exception as exc:
        logger.error(f"Error parsing webhook data: {exc}")
        return ERROR_STATUS

    message_data = await extract_message_content(webhook_data)
    if not message_data:
        return OK_STATUS

    user_number, incoming_msg, message_id = message_data

    # Create message and enqueue it
    msg = Message(user_number=user_number, content=incoming_msg, message_id=message_id)
    await message_queue.enqueue(msg)

    # Start processing queue for this user if not already running
    await message_queue.start_processing(user_number, _process_message)

    # Notify user if queue is building up
    queue_size = message_queue.queue_size(user_number)
    if queue_size > 1:
        logger.warning(f"Queue size for {user_number} is {queue_size}")

    return OK_STATUS
