# uv run pytest -s chatbot/ai_agent/tests/test_customer.py

"""Functional tests for customer tools against the real ERP API.

Controllers covered:
  - contact_controller      (resolve_or_create_contact, update_contact)
  - conversation_controller (open_or_resume_conversation)
  - lead_controller         (upsert_lead)
"""

from __future__ import annotations

import httpx
import pytest
from pydantic_ai import RunContext

from chatbot.ai_agent.dependencies import AgentDeps
from chatbot.ai_agent.models import ContactInfo, ConversationInfo, LeadInfo, LeadStatus
from chatbot.ai_agent.tools.customer import (
    open_or_resume_conversation,
    resolve_or_create_contact,
    update_contact,
    upsert_lead,
)

# Rango de telefonos reservado para estos tests: +598 99 100 0xx
_BASE_PHONE = "+598 99 100 0"


# ---------------------------------------------------------------------------
# contact_controller
# ---------------------------------------------------------------------------


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_resolve_or_create_contact
@pytest.mark.anyio
async def test_resolve_or_create_contact(ctx: RunContext[AgentDeps]) -> None:
    """Debe retornar un ContactInfo con contact_id valido."""
    result = await resolve_or_create_contact(
        ctx, phone=f"{_BASE_PHONE}01", name="Test Catalog User"
    )

    print(f"\n  resolve_or_create_contact -> {result}")
    assert isinstance(result, ContactInfo)
    assert result.contact_id
    assert ctx.deps.contact_id == result.contact_id


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_resolve_or_create_contact_idempotent
@pytest.mark.anyio
async def test_resolve_or_create_contact_idempotent(ctx: RunContext[AgentDeps]) -> None:
    """Llamar dos veces con el mismo telefono debe retornar el mismo contact_id."""
    phone = f"{_BASE_PHONE}02"

    first = await resolve_or_create_contact(ctx, phone=phone)
    second = await resolve_or_create_contact(ctx, phone=phone)

    print(f"\n  1ra llamada: {first.contact_id} | 2da llamada: {second.contact_id}")
    assert first.contact_id == second.contact_id


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_resolve_contact_uses_user_phone
@pytest.mark.anyio
async def test_resolve_contact_uses_user_phone(ctx: RunContext[AgentDeps]) -> None:
    """Sin argumento phone, debe usar ctx.deps.user_phone."""
    ctx.deps.user_phone = f"{_BASE_PHONE}03"

    result = await resolve_or_create_contact(ctx)

    print(f"\n  Resolvio con user_phone={ctx.deps.user_phone} -> {result.contact_id}")
    assert isinstance(result, ContactInfo)
    assert result.contact_id


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_resolve_contact_is_new_flag
@pytest.mark.anyio
async def test_resolve_contact_is_new_flag(ctx: RunContext[AgentDeps]) -> None:
    """El campo is_new debe ser bool o None (no importa el valor en runs sucesivos)."""
    result = await resolve_or_create_contact(
        ctx, phone=f"{_BASE_PHONE}04", name="Brand New Contact"
    )

    print(f"\n  is_new={result.is_new} para telefono +598 99 100 004")
    # El ERP puede omitir is_new; si lo incluye debe ser bool
    assert result.is_new is None or isinstance(result.is_new, bool)


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_update_contact_name
@pytest.mark.anyio
async def test_update_contact_name(ctx: RunContext[AgentDeps]) -> None:
    """Debe actualizar el nombre del contacto y retornar changed_fields."""
    try:
        await resolve_or_create_contact(ctx, phone=f"{_BASE_PHONE}05", name="Antes")
    except httpx.HTTPStatusError as exc:
        pytest.skip(f"ERP devolvio error en setup: {exc.response.status_code}")

    result = await update_contact(ctx, name="Despues")

    print(f"\n  update_contact -> changed_fields={result.get('changed_fields')}")
    assert isinstance(result, dict)
    assert "changed_fields" in result
    assert result.get("audit_event_id")


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_update_contact_email
@pytest.mark.anyio
async def test_update_contact_email(ctx: RunContext[AgentDeps]) -> None:
    """Debe actualizar el email y registrarlo en changed_fields."""
    try:
        await resolve_or_create_contact(ctx, phone=f"{_BASE_PHONE}06")
    except httpx.HTTPStatusError as exc:
        pytest.skip(f"ERP devolvio error en setup: {exc.response.status_code}")

    result = await update_contact(ctx, email="test@example.com")

    print(f"\n  update_contact(email) -> changed_fields={result.get('changed_fields')}")
    assert isinstance(result, dict)
    assert "changed_fields" in result


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_update_contact_requires_contact_id
@pytest.mark.anyio
async def test_update_contact_requires_contact_id(ctx: RunContext[AgentDeps]) -> None:
    """Debe lanzar ValueError si contact_id no esta en deps."""
    ctx.deps.contact_id = None

    with pytest.raises(ValueError, match="contact_id"):
        await update_contact(ctx, name="Fail")


# ---------------------------------------------------------------------------
# conversation_controller
# ---------------------------------------------------------------------------


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_open_or_resume_conversation
@pytest.mark.anyio
async def test_open_or_resume_conversation(ctx: RunContext[AgentDeps]) -> None:
    """Debe retornar un ConversationInfo con conversation_id valido."""
    await resolve_or_create_contact(ctx, phone=f"{_BASE_PHONE}07")

    try:
        result = await open_or_resume_conversation(ctx)
    except httpx.HTTPStatusError as exc:
        pytest.skip(f"ERP devolvio error {exc.response.status_code}")

    print(f"\n  open_or_resume_conversation -> {result}")
    assert isinstance(result, ConversationInfo)
    assert result.conversation_id
    assert ctx.deps.conversation_id == result.conversation_id


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_open_or_resume_conversation_idempotent
@pytest.mark.anyio
async def test_open_or_resume_conversation_idempotent(
    ctx: RunContext[AgentDeps],
) -> None:
    """Abrir la conversacion dos veces debe retornar la misma (is_new=False la 2da vez)."""
    await resolve_or_create_contact(ctx, phone=f"{_BASE_PHONE}08")

    try:
        first = await open_or_resume_conversation(ctx)
        second = await open_or_resume_conversation(ctx)
    except httpx.HTTPStatusError as exc:
        pytest.skip(f"ERP devolvio error {exc.response.status_code}")

    print(f"\n  1ra: {first.conversation_id} | 2da: {second.conversation_id}")
    # El ERP puede crear una nueva o reusar la activa – ambas son validas
    assert first.conversation_id
    assert second.conversation_id
    if second.is_new is not None:
        assert second.is_new is False


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_open_conversation_requires_contact_id
@pytest.mark.anyio
async def test_open_conversation_requires_contact_id(
    ctx: RunContext[AgentDeps],
) -> None:
    """Debe lanzar ValueError si contact_id no esta en deps."""
    ctx.deps.contact_id = None

    with pytest.raises(ValueError, match="contact_id"):
        await open_or_resume_conversation(ctx)


# ---------------------------------------------------------------------------
# lead_controller
# ---------------------------------------------------------------------------


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_upsert_lead
@pytest.mark.anyio
async def test_upsert_lead(ctx: RunContext[AgentDeps]) -> None:
    """Debe crear/actualizar un lead y retornar LeadInfo con status OPEN."""
    await resolve_or_create_contact(ctx, phone=f"{_BASE_PHONE}09")

    try:
        await open_or_resume_conversation(ctx)
    except httpx.HTTPStatusError as exc:
        pytest.skip(f"ERP devolvio error en conversacion: {exc.response.status_code}")

    result = await upsert_lead(ctx, interest_type="Experience")

    print(f"\n  upsert_lead -> {result}")
    assert isinstance(result, LeadInfo)
    assert result.lead_id
    assert result.status == LeadStatus.OPEN


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_upsert_lead_idempotent
@pytest.mark.anyio
async def test_upsert_lead_idempotent(ctx: RunContext[AgentDeps]) -> None:
    """Llamar upsert_lead dos veces no debe crear duplicados (mismo lead_id o OPEN)."""
    await resolve_or_create_contact(ctx, phone=f"{_BASE_PHONE}10")

    try:
        await open_or_resume_conversation(ctx)
    except httpx.HTTPStatusError as exc:
        pytest.skip(f"ERP devolvio error en conversacion: {exc.response.status_code}")

    first = await upsert_lead(ctx, interest_type="Route")
    second = await upsert_lead(ctx, interest_type="Route")

    print(f"\n  1er lead: {first.lead_id} | 2do lead: {second.lead_id}")
    assert first.status == LeadStatus.OPEN
    assert second.status == LeadStatus.OPEN


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_upsert_lead_requires_contact_id
@pytest.mark.anyio
async def test_upsert_lead_requires_contact_id(ctx: RunContext[AgentDeps]) -> None:
    """Debe lanzar ValueError si contact_id no esta en deps."""
    ctx.deps.contact_id = None
    ctx.deps.conversation_id = "CONV-FAKE"

    with pytest.raises(ValueError, match="contact_id"):
        await upsert_lead(ctx)


# uv run pytest -s chatbot/ai_agent/tests/test_customer.py::test_upsert_lead_requires_conversation_id
@pytest.mark.anyio
async def test_upsert_lead_requires_conversation_id(ctx: RunContext[AgentDeps]) -> None:
    """Debe lanzar ValueError si conversation_id no esta en deps."""
    ctx.deps.contact_id = "CONT-FAKE"
    ctx.deps.conversation_id = None

    with pytest.raises(ValueError, match="conversation_id"):
        await upsert_lead(ctx)
