
from pydantic import BaseModel, Field


class DonationCreateOrder(BaseModel):
    donor_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    phone: str = Field(min_length=7, max_length=20)

    # Donor's place or city
    place: str = Field(min_length=1, max_length=200)

    # Amount is selected by the donor
    amount: float = Field(
        gt=0,
        le=10000000
    )


class DonationPaymentVerify(BaseModel):
    donation_id: str = Field(min_length=1)
    razorpay_order_id: str = Field(min_length=1)
    razorpay_payment_id: str = Field(min_length=1)
    razorpay_signature: str = Field(min_length=1)
