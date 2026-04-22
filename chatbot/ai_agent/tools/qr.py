from __future__ import annotations

import logging

import httpx
from pydantic import ValidationError
from pydantic_ai import RunContext

from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.ai_agent.models import (
    ERP_BASE_PATH,
    PaymentInstructions,
    ReservationStatusDetail,
)
from chatbot.ai_agent.tools.erp_utils import extract_erp_data
from chatbot.api.utils.qr import (
    build_qr_caption,
    build_qr_image_url,
    fetch_reservation_qr,
)
from chatbot.messaging.whatsapp import _ensure_rgb_png

logger = logging.getLogger(__name__)

QR_IMAGE_TIMEOUT_SECONDS: float = 15.0
ERP_TIMEOUT_SECONDS: float = 15.0


async def _validate_qr_eligibility(
    erp_client: httpx.AsyncClient, ticket_id: str
) -> str | None:
    """Check that the ticket is CONFIRMED and has the deposit fully paid.

    Returns an error message string if the ticket is not eligible, or None if it is.
    """
    # 1. Check reservation status
    try:
        status_resp = await erp_client.post(
            f"{ERP_BASE_PATH}.ticket_controller.get_reservation_status",
            json={"reservation_id": ticket_id},
            timeout=ERP_TIMEOUT_SECONDS,
        )
        status_resp.raise_for_status()
        detail = ReservationStatusDetail.model_validate(
            extract_erp_data(status_resp.json())
        )
    except Exception as exc:
        logger.warning(
            "[send_checkin_qr] Could not verify ticket status for %s: %s",
            ticket_id,
            exc,
        )
        return "Could not verify the ticket status. Please try again later."

    if (detail.status or "").lower() != "confirmed":
        logger.info(
            "[send_checkin_qr] Ticket %s not CONFIRMED (status=%s) — QR denied",
            ticket_id,
            detail.status,
        )
        return (
            f"The QR code for ticket {ticket_id} is not available because the reservation "
            f"is not in CONFIRMED status (current status: {detail.status})."
        )

    # 2. Check deposit payment — skip if deposit is not required
    if not detail.deposit_required:
        return None

    try:
        dep_resp = await erp_client.post(
            f"{ERP_BASE_PATH}.deposit_controller.get_deposit_instructions",
            json={"ticket_id": ticket_id},
            timeout=ERP_TIMEOUT_SECONDS,
        )
        dep_resp.raise_for_status()
        instructions = PaymentInstructions.model_validate(
            extract_erp_data(dep_resp.json())
        )
    except Exception as exc:
        logger.warning(
            "[send_checkin_qr] Could not verify deposit for ticket %s: %s",
            ticket_id,
            exc,
        )
        return "Could not verify the deposit payment. Please try again later."

    if instructions.amount_remaining is not None and instructions.amount_remaining > 0:
        logger.info(
            "[send_checkin_qr] Ticket %s has pending deposit (amount_remaining=%.2f) — QR denied",
            ticket_id,
            instructions.amount_remaining,
        )
        return (
            f"The QR code for ticket {ticket_id} is not available yet because the deposit "
            f"payment has not been completed. Pending amount: {instructions.amount_remaining}."
        )

    return None


async def send_checkin_qr(ctx: RunContext[AgentDeps], ticket_id: str) -> str:
    """Send the check-in QR image for a reservation to the user.

    Fetch the QR token from the ERP, download the image and deliver it via
    the current messaging channel (WhatsApp or Telegram).  Use this tool
    when the client explicitly asks for their check-in QR or says they did
    not receive it.  The ticket must be in CONFIRMED status and the deposit
    payment must be fully completed.

    Args:
        ctx: Agent run context with dependencies.
        ticket_id: The reservation ticket ID (e.g. TKT-2026-03-00067).
    """
    logger.info("[send_checkin_qr] ticket_id=%s", ticket_id)

    error_msg = await _validate_qr_eligibility(ctx.deps.erp_client, ticket_id)
    if error_msg:
        return error_msg

    if ctx.deps.send_photo_callback is None:
        return (
            "I cannot send images through the current channel. "
            "Please ask the establishment to share the QR with you directly."
        )

    try:
        qr_data = await fetch_reservation_qr(
            erp_client=ctx.deps.erp_client, ticket_id=ticket_id
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return f"No QR found for ticket {ticket_id}. Please verify the ticket ID."
        logger.error("[send_checkin_qr] ERP error for ticket=%s: %s", ticket_id, exc)
        return "Failed to retrieve the QR from the system. Please try again later."
    except (httpx.HTTPError, ValidationError, ValueError) as exc:
        logger.error(
            "[send_checkin_qr] Error fetching QR for ticket=%s: %s", ticket_id, exc
        )
        return "Failed to retrieve the QR from the system. Please try again later."

    qr_image_url = build_qr_image_url(qr_data.qr_image_url)
    caption = build_qr_caption(ticket_id=qr_data.ticket_id, token=qr_data.token)

    try:
        async with httpx.AsyncClient(timeout=QR_IMAGE_TIMEOUT_SECONDS) as client:
            img_resp = await client.get(qr_image_url)
            img_resp.raise_for_status()
            image_bytes = _ensure_rgb_png(img_resp.content)
    except httpx.HTTPError as exc:
        logger.error(
            "[send_checkin_qr] Failed to download QR image for ticket=%s: %s",
            ticket_id,
            exc,
        )
        return "Failed to download the QR image. Please try again later."

    try:
        await ctx.deps.send_photo_callback(image_bytes, caption)
    except Exception as exc:
        logger.error(
            "[send_checkin_qr] Failed to deliver QR image for ticket=%s: %s",
            ticket_id,
            exc,
        )
        return "The QR was found but could not be delivered. Please try again later."

    logger.info("[send_checkin_qr] QR sent for ticket=%s", ticket_id)
    return f"Check-in QR for ticket {ticket_id} sent successfully."
