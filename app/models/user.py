from pydantic import BaseModel
from typing import Optional


class UserCreate(BaseModel):

    name: str

    email: str

    phone: Optional[str] = None

    password: str

    role: str = "User"


class UserUpdate(BaseModel):

    name: Optional[str] = None

    email: Optional[str] = None

    phone: Optional[str] = None

    password: Optional[str] = None

    role: Optional[str] = None