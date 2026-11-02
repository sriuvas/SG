from pydantic import BaseModel, Field
from typing import Optional


class EventRegistrationCreate(BaseModel):
    event_id: str = Field(
        min_length=1
    )

    name: str = Field(
        min_length=1,
        max_length=200
    )

    email: str = Field(
        min_length=3,
        max_length=320
    )

    phone: str = Field(
        min_length=7,
        max_length=20
    )

    gothram: Optional[str] = Field(
        default=None,
        max_length=100
    )

    nakshatram: Optional[str] = Field(
        default=None,
        max_length=100
    )

    attendees_count: int = Field(
        default=1,
        ge=1,
        le=20
    )


class EventRegistrationPaymentVerify(BaseModel):
    registration_id: str = Field(
        min_length=1
    )

    razorpay_order_id: str = Field(
        min_length=1
    )

    razorpay_payment_id: str = Field(
        min_length=1
    )

    razorpay_signature: str = Field(
        min_length=1
    )


class EventRegistrationResponse(BaseModel):
    registration_id: str
    event_id: str
    user_id: str
    devotee_name: str
    email: str
    phone: str
    gothram: Optional[str] = None
    nakshatram: Optional[str] = None
    attendees_count: int
    unit_price: float
    total_amount: float
    status: str
    transaction_id: str
    receipt_number: str
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    created_at: str
    updated_at: str