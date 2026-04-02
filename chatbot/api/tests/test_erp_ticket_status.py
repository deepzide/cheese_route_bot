# uv run pytest -s chatbot/api/tests/test_erp_ticket_status.py

from fastapi import HTTPException

from chatbot.ai_agent.models import (
    ContactInfo,
    ERPTicketStatusRequest,
    ReservationContactDetail,
    ReservationStatusDetail,
    TicketDecision,
)
from chatbot.api.erp_router import (
    _build_ticket_message,
    _validate_ticket_status_payload,
)


# uv run pytest -s chatbot/api/tests/test_erp_ticket_status.py
def test_ticket_status_request_normalizes_hyphenated_statuses() -> None:
    checked_in_request = ERPTicketStatusRequest(
        contact_id="CONTACT-1",
        ticket_id="TICKET-1",
        new_status="Checked-In",
    )
    no_show_request = ERPTicketStatusRequest(
        contact_id="CONTACT-1",
        ticket_id="TICKET-1",
        new_status="No-Show",
    )

    assert checked_in_request.new_status == TicketDecision.CHECKED_IN
    assert no_show_request.new_status == TicketDecision.NO_SHOW


# uv run pytest -s chatbot/api/tests/test_erp_ticket_status.py
def test_validate_ticket_status_payload_accepts_matching_contact_and_status() -> None:
    body = ERPTicketStatusRequest(
        contact_id="CONTACT-1",
        ticket_id="TICKET-1",
        new_status="Cancelled",
    )
    contact = ContactInfo(contact_id="CONTACT-1", phone="+59899000000")
    ticket = ReservationStatusDetail(
        ticket_id="TICKET-1",
        status="CANCELLED",
        contact=ReservationContactDetail(contact_id="CONTACT-1"),
    )

    _validate_ticket_status_payload(body=body, contact=contact, ticket=ticket)


# uv run pytest -s chatbot/api/tests/test_erp_ticket_status.py
def test_validate_ticket_status_payload_rejects_ticket_from_other_contact() -> None:
    body = ERPTicketStatusRequest(
        contact_id="CONTACT-1",
        ticket_id="TICKET-1",
        new_status="Rejected",
    )
    contact = ContactInfo(contact_id="CONTACT-1", phone="+59899000000")
    ticket = ReservationStatusDetail(
        ticket_id="TICKET-1",
        status="REJECTED",
        contact=ReservationContactDetail(contact_id="CONTACT-2"),
    )

    try:
        _validate_ticket_status_payload(body=body, contact=contact, ticket=ticket)
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail == "El ticket TICKET-1 no pertenece al contacto CONTACT-1"
    else:
        raise AssertionError(
            "Se esperaba HTTPException cuando el ticket no pertenece al contacto"
        )


# uv run pytest -s chatbot/api/tests/test_erp_ticket_status.py
def test_validate_ticket_status_payload_rejects_status_mismatch() -> None:
    body = ERPTicketStatusRequest(
        contact_id="CONTACT-1",
        ticket_id="TICKET-1",
        new_status="Expired",  # type: ignore
    )
    contact = ContactInfo(contact_id="CONTACT-1", phone="+59899000000")
    ticket = ReservationStatusDetail(
        ticket_id="TICKET-1",
        status="REJECTED",
        contact=ReservationContactDetail(contact_id="CONTACT-1"),
    )

    try:
        _validate_ticket_status_payload(body=body, contact=contact, ticket=ticket)
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "no coincide con el nuevo estado recibido" in exc.detail
    else:
        raise AssertionError(
            "Se esperaba HTTPException cuando el estado del ERP no coincide"
        )


# uv run pytest -s chatbot/api/tests/test_erp_ticket_status.py
def test_build_ticket_message_supports_requested_statuses() -> None:
    expected_snippets = {
        TicketDecision.CANCELLED: "has been *cancelled*",
        TicketDecision.NO_SHOW: "*no show*",
        TicketDecision.EXPIRED: "has *expired*",
        TicketDecision.REJECTED: "has been *rejected*",
        TicketDecision.CHECKED_IN: "*check-in*",
    }

    for decision, snippet in expected_snippets.items():
        message = _build_ticket_message(decision, "TICKET-1", "Observacion.")

        assert "TICKET-1" in message
        assert snippet in message
        assert "Observacion." in message
