from pydantic import BaseModel
from typing import Optional


class CommitteeCreate(BaseModel):

    member_name: str

    designation: str

    role: str

    responsibility: str

    profile: Optional[str] = None

    photo_url: Optional[str] = None


class CommitteeUpdate(BaseModel):

    member_name: Optional[str] = None

    designation: Optional[str] = None

    role: Optional[str] = None

    responsibility: Optional[str] = None

    profile: Optional[str] = None

    photo_url: Optional[str] = None