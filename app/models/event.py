from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal


# ==================================================
# CREATE EVENT
# ==================================================

class EventCreate(BaseModel):

    event_name: str

    event_date: str

    start_time: str

    end_time: str

    location: str

    description: str

    image_url: Optional[str] = None

    instructions: Optional[str] = None

    registration_required: bool = False

    contact_info: Optional[str] = None

    # Admin-defined event price
    # 0.00 = Free event
    # Greater than 0 = Paid event
    price: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=10,
        decimal_places=2
    )


# ==================================================
# UPDATE EVENT
# ==================================================

class EventUpdate(BaseModel):

    event_name: Optional[str] = None

    event_date: Optional[str] = None

    start_time: Optional[str] = None

    end_time: Optional[str] = None

    location: Optional[str] = None

    description: Optional[str] = None

    image_url: Optional[str] = None

    instructions: Optional[str] = None

    registration_required: Optional[bool] = None

    contact_info: Optional[str] = None

    # Admin can modify the event price
    # 0.00 = Free event
    # Greater than 0 = Paid event
    # Negative values are rejected
    price: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=10,
        decimal_places=2
    )