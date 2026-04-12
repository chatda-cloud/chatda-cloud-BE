from datetime import date
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


# ── 회원가입 ──────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    username: str
    gender: Optional[str] = None    # M | F
    birthDate: Optional[date] = None

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다.")
        return v

    @field_validator("username")
    @classmethod
    def username_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("닉네임을 입력해주세요.")
        return v.strip()

    @field_validator("gender")
    @classmethod
    def gender_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("M", "F"):
            raise ValueError("gender는 M | F 중 하나여야 합니다.")
        return v


# ── 로그인 ──────────────────────────────────────────────────────────────────

class SigninRequest(BaseModel):
    email: EmailStr
    password: str


# ── 소셜 로그인 코드 교환 ──────────────────────────────────────────────────────

class SocialExchangeRequest(BaseModel):
    provider: str   # kakao | google | apple
    code: str


# ── 토큰 재발급 ───────────────────────────────────────────────────────────────

class TokenReissueRequest(BaseModel):
    refreshToken: str


# ── 비밀번호 재설정 ───────────────────────────────────────────────────────────

class PwResetRequestBody(BaseModel):
    email: EmailStr


class PwResetConfirmBody(BaseModel):
    token: str
    newPassword: str

    @field_validator("newPassword")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다.")
        return v


# ── 응답 ─────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    accessToken: str
    refreshToken: str
    id: int
    username: str
    email: str
    tokenType: str = "bearer"
