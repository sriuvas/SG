from pydantic import BaseModel
from typing import Optional


class AnnouncementCreate(BaseModel):

    title: str

    description: str

    announcement_date: str

    image_url: Optional[str] = None

    is_published: bool = True


class AnnouncementUpdate(BaseModel):

    title: Optional[str] = None

    description: Optional[str] = None

    announcement_date: Optional[str] = None

    image_url: Optional[str] = None

    is_published: Optional[bool] = None