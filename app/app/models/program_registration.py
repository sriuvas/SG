from pydantic import BaseModel, Field
from typing import Optional


# ==================================================
# Create Program Registration
# ==================================================

class ProgramRegistrationCreate(BaseModel):

    program_id: str = Field(
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


# ==================================================
# Verify Razorpay Payment
# ==================================================

class ProgramRegistrationPaymentVerify(BaseModel):

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