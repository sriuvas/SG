from pydantic import BaseModel
from typing import Optional


# ==================================================
# Create Goshala
# ==================================================

class GoshalaCreate(BaseModel):

    title: str

    description: str

    history: Optional[str] = None

    activities: Optional[str] = None

    facilities: Optional[str] = None

    cow_care: Optional[str] = None

    support_info: Optional[str] = None

    donation_info: Optional[str] = None

    image_url: Optional[str] = None


# ==================================================
# Update Goshala
# ==================================================

class GoshalaUpdate(BaseModel):

    title: Optional[str] = None

    description: Optional[str] = None

    history: Optional[str] = None

    activities: Optional[str] = None

    facilities: Optional[str] = None

    cow_care: Optional[str] = None

    support_info: Optional[str] = None

    donation_info: Optional[str] = None

    image_url: Optional[str] = None