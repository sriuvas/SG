
from pydantic import BaseModel, Field, SecretStr, model_validator
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


class ChangePasswordRequest(BaseModel):

    old_password: SecretStr = Field(min_length=1)

    new_password: SecretStr = Field(min_length=8, max_length=128)

    confirm_password: SecretStr = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_passwords(self):
        old_password = self.old_password.get_secret_value()
        new_password = self.new_password.get_secret_value()
        confirm_password = self.confirm_password.get_secret_value()

        if new_password != confirm_password:
            raise ValueError(
                "New password and confirm password do not match"
            )

        if new_password == old_password:
            raise ValueError(
                "New password must be different from old password"
            )

        return self
