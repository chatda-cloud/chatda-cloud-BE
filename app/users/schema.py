from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class UserCreate(BaseModel):
    user_id: str
    password: str
    email: EmailStr
    phone: str | None = None

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if len(v) < 4:
            raise ValueError("아이디는 4자 이상이어야 합니다.")
        if len(v) > 30:
            raise ValueError("아이디는 30자 이하여야 합니다.")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다.")
        return v


class UserResponse(BaseModel):
    id: int
    user_id: str
    email: str
    phone: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateFcmToken(BaseModel):
    fcm_token: str