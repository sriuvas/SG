from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal


class ProgramCreate(BaseModel):

    program_name: str

    description: str

    program_date: str

    start_time: str

    end_time: str

    location: str

    schedule: Optional[str] = None

    image_url: Optional[str] = None

    participation_info: Optional[str] = None

    contact_info: Optional[str] = None

    price: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        max_digits=10,
        decimal_places=2
    )


class ProgramUpdate(BaseModel):

    program_name: Optional[str] = None

    description: Optional[str] = None

    program_date: Optional[str] = None

    start_time: Optional[str] = None

    end_time: Optional[str] = None

    location: Optional[str] = None

    schedule: Optional[str] = None

    image_url: Optional[str] = None

    participation_info: Optional[str] = None

    contact_info: Optional[str] = None

    price: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0.00"),
        max_digits=10,
        decimal_places=2
    )