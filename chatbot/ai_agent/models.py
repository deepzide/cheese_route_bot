"""Pydantic models for agent I/O and ERP API data structures.

All models that represent data coming from the ERP use Pydantic (external data).
Internal-only structures use dataclass (see dependencies.py, context.py).

ERP base: https://erp-cheese.deepzide.com
All endpoints are POST under /api/method/cheese.api.v1.<controller>.<method>
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# ERP API path constants
# ---------------------------------------------------------------------------

ERP_BASE_PATH: str = "https://erp-cheese.deepzide.com/api/method/cheese.api.v1"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReservationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    COMPLETED = "completed"


class LeadStatus(StrEnum):
    OPEN = "OPEN"
    NOT_CONVERTED = "not converted"
    CONVERTED = "converted"


# ---------------------------------------------------------------------------
# 1. Contact
# ---------------------------------------------------------------------------


class ContactInfo(BaseModel):
    """CRM contact resolved or created by the ERP."""

    contact_id: str
    phone: str | None = None
    name: str | None = None
    email: str | None = None
    is_new: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # ERP sends full_name instead of name
            if "full_name" in data and "name" not in data:
                data["name"] = data["full_name"]
        return data


class UpdateContactRequest(BaseModel):
    """Body for update_contact."""

    contact_id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    idempotency_key: str | None = None


# ---------------------------------------------------------------------------
# 2. Conversation
# ---------------------------------------------------------------------------


class ConversationInfo(BaseModel):
    """Persistent conversation returned by the ERP."""

    conversation_id: str
    contact_id: str | None = None
    channel: str | None = None
    status: str | None = None
    is_new: bool | None = None


class ConversationEvent(BaseModel):
    """Event appended to a conversation."""

    conversation_id: str
    event_type: str
    event_data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 3. Leads
# ---------------------------------------------------------------------------


class LeadInfo(BaseModel):
    """CRM lead record."""

    lead_id: str | None = None
    contact_id: str | None = None
    status: LeadStatus = LeadStatus.NOT_CONVERTED
    interest_type: str | None = None


# ---------------------------------------------------------------------------
# 4. Catalog – Experiences
# ---------------------------------------------------------------------------


class Experience(BaseModel):
    """Bookable experience from the ERP catalog."""

    experience_id: str
    name: str
    description: str | None = None
    establishment_id: str | None = None
    price: float | None = None
    currency: str = "UYU"
    duration_minutes: int | None = None
    requires_deposit: bool = False
    package_only: bool = False
    is_online: bool = True

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:  # noqa: C901
        if isinstance(data, dict):
            # ERP sends "id" or "name" as identifier
            if "experience_id" not in data:
                data["experience_id"] = data.get("id", data.get("name", ""))
            # ERP sends "experience_name" instead of "name"
            if "experience_name" in data and "name" not in data:
                data["name"] = data["experience_name"]
            # ERP sends "status": "ONLINE" instead of "is_online"
            if "status" in data and "is_online" not in data:
                data["is_online"] = data["status"] == "ONLINE"
            # ERP sends "individual_price" and "route_price"
            if "individual_price" in data and "price" not in data:
                data["price"] = data["individual_price"]
            # ERP sends "deposit_required": 1/0
            if "deposit_required" in data and "requires_deposit" not in data:
                data["requires_deposit"] = bool(data["deposit_required"])
            # ERP sends "establishment" instead of "establishment_id"
            if "establishment" in data and "establishment_id" not in data:
                data["establishment_id"] = data["establishment"]
            # ERP sends "package_mode": "Both"/"Individual"/"Route"
            if "package_mode" in data and "package_only" not in data:
                data["package_only"] = data["package_mode"] == "Route"
        return data


# ---------------------------------------------------------------------------
# 5. Catalog – Routes
# ---------------------------------------------------------------------------


class Route(BaseModel):
    """Pre-assembled themed route."""

    route_id: str
    name: str
    description: str | None = None
    experiences: list[dict[str, Any]] = Field(default_factory=list)
    total_price: float | None = None
    currency: str = "UYU"

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "route_id" not in data:
                data["route_id"] = data.get("id", data.get("name", ""))
            # ERP sends "route_name" instead of "name"
            if "route_name" in data and "name" not in data:
                data["name"] = data["route_name"]
            # ERP sends "price" instead of "total_price"
            if "price" in data and "total_price" not in data:
                data["total_price"] = data["price"]
        return data


# ---------------------------------------------------------------------------
# 6. Availability
# ---------------------------------------------------------------------------


class TimeSlot(BaseModel):
    """Available time slot for a given experience/date."""

    slot_id: str
    start: datetime | None = None
    end: datetime | None = None
    available_capacity: int | None = None


class AvailabilityResponse(BaseModel):
    """Result of an availability lookup."""

    experience_id: str | None = None
    route_id: str | None = None
    date: str | None = None
    slots: list[TimeSlot] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 7. Pricing and Policies
# ---------------------------------------------------------------------------


class PricingPreview(BaseModel):
    """Pricing breakdown returned before booking."""

    total_price: float | None = None
    deposit_amount: float | None = None
    currency: str = "UYU"
    breakdown: list[dict[str, Any]] = Field(default_factory=list)


class ModificationPolicy(BaseModel):
    """What can be modified and associated cost."""

    allowed: bool = False
    modifiable_fields: list[str] = Field(default_factory=list)
    fee: float | None = None
    message: str | None = None


class CancellationImpact(BaseModel):
    """Penalties and consequences of a cancellation."""

    allowed: bool = False
    penalty: float | None = None
    refund_amount: float | None = None
    message: str | None = None


# ---------------------------------------------------------------------------
# 8. Individual Reservations
# ---------------------------------------------------------------------------


class ReservationResponse(BaseModel):
    """Individual reservation created/returned by the ERP."""

    reservation_id: str
    status: ReservationStatus = ReservationStatus.PENDING
    experience_id: str | None = None
    experience_name: str | None = None
    date: str | None = None
    slot_id: str | None = None
    party_size: int | None = None
    confirmation_code: str | None = None
    next_steps: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "reservation_id" not in data:
                data["reservation_id"] = data.get("id", data.get("name", ""))
        return data


class ModificationPreview(BaseModel):
    """Preview of the impact of a reservation modification."""

    preview_id: str | None = None
    changes: list[dict[str, Any]] = Field(default_factory=list)
    price_delta: float | None = None
    message: str | None = None


# ---------------------------------------------------------------------------
# 9. Route Reservations
# ---------------------------------------------------------------------------


class RouteBookingResponse(BaseModel):
    """Route booking (aggregated reservation for a route)."""

    route_booking_id: str
    route_id: str | None = None
    status: ReservationStatus = ReservationStatus.PENDING
    reservations: list[ReservationResponse] = Field(default_factory=list)
    summary: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "route_booking_id" not in data:
                data["route_booking_id"] = data.get("id", data.get("name", ""))
        return data


# ---------------------------------------------------------------------------
# 10. Mixed Booking
# ---------------------------------------------------------------------------


class BookingResponse(BaseModel):
    """Mixed booking aggregator – may contain route + individual reservations."""

    booking_id: str
    status: ReservationStatus = ReservationStatus.PENDING
    route_booking: RouteBookingResponse | None = None
    individual_reservations: list[ReservationResponse] = Field(default_factory=list)
    total_price: float | None = None
    currency: str = "UYU"

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "booking_id" not in data:
                data["booking_id"] = data.get("id", data.get("name", ""))
        return data


# ---------------------------------------------------------------------------
# 11. Payment
# ---------------------------------------------------------------------------


class PaymentInstructions(BaseModel):
    """Payment link or instructions for a reservation / booking."""

    payment_link: str | None = None
    instructions: str | None = None
    deposit_amount: float | None = None
    currency: str = "UYU"


class PaymentStatus(BaseModel):
    """Consolidated payment status."""

    status: str | None = None
    amount_paid: float | None = None
    amount_due: float | None = None
    currency: str = "UYU"


# ---------------------------------------------------------------------------
# 12. QR and Check-in
# ---------------------------------------------------------------------------


class QRInfo(BaseModel):
    """QR data for check-in."""

    qr_token: str | None = None
    qr_url: str | None = None
    reservation_id: str | None = None


class CheckinStatus(BaseModel):
    """Check-in status for a reservation."""

    reservation_id: str | None = None
    checked_in: bool = False
    checked_in_at: datetime | None = None


# ---------------------------------------------------------------------------
# 13. Itinerary
# ---------------------------------------------------------------------------


class ItineraryResponse(BaseModel):
    """Customer itinerary with all their reservations."""

    contact_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 14. Survey and Complaints
# ---------------------------------------------------------------------------


class SurveyRequest(BaseModel):
    """Survey request created for a completed ticket."""

    survey_id: str | None = None
    ticket_id: str | None = None
    status: str | None = None


class SurveySubmission(BaseModel):
    """Survey response submitted by the user."""

    survey_id: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class ComplaintResponse(BaseModel):
    """Complaint / support case created in the ERP."""

    complaint_id: str | None = None
    contact_id: str | None = None
    status: str | None = None
    message: str | None = None


# ---------------------------------------------------------------------------
# Establishment (additional)
# ---------------------------------------------------------------------------


class Establishment(BaseModel):
    """Establishment / producer from the ERP catalog."""

    establishment_id: str | None = None
    name: str
    type: str | None = None
    description: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    payment_methods: list[str] = Field(default_factory=list)
    status: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # ERP sends "company_id" instead of "establishment_id"
            if "establishment_id" not in data:
                data["establishment_id"] = data.get(
                    "company_id", data.get("id", data.get("name", ""))
                )
            # ERP sends "company_name" instead of "name"
            if "company_name" in data and "name" not in data:
                data["name"] = data["company_name"]
        return data


# ---------------------------------------------------------------------------
# Webhook event models (ERP → Bot)
# ---------------------------------------------------------------------------


class WebhookEvent(BaseModel):
    """Base model for any ERP webhook event."""

    event_type: str
    reservation_id: str | None = None
    booking_id: str | None = None
    contact_phone: str
    timestamp: datetime = Field(default_factory=datetime.now)
    payload: dict[str, Any] = Field(default_factory=dict)
