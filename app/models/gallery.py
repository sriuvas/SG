from pydantic import BaseModel
from typing import Optional


# ==================================================
# Create Gallery Image
# ==================================================

class GalleryCreate(BaseModel):

    image_url: str

    title: str

    description: Optional[str] = None

    category: str

    upload_date: str


# ==================================================
# Update Gallery Image
# ==================================================

class GalleryUpdate(BaseModel):

    image_url: Optional[str] = None

    title: Optional[str] = None

    description: Optional[str] = None

    category: Optional[str] = None

    upload_date: Optional[str] = None