from pydantic import BaseModel
from typing import Optional


class NakshatraCreate(BaseModel):

    nakshatra_name: str

    description: str

    deity: Optional[str] = None

    characteristics: Optional[str] = None

    significance: Optional[str] = None


class NakshatraUpdate(BaseModel):

    nakshatra_name: Optional[str] = None

    description: Optional[str] = None

    deity: Optional[str] = None

    characteristics: Optional[str] = None

    significance: Optional[str] = None


class NakshatraCalculate(BaseModel):

    name: str

    date_of_birth: str

    birth_time: str