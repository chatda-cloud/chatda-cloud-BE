"""auth 비즈니스 로직."""
import asyncio
import logging
import secrets
import smtplib
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET,
    PW_RESET_BASE_URL,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_SENDER,
    SMTP_USER,
)
from app.models import User

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PW_RESET_EXPIRE_MINUTES = 30


# ── 비밀번호 ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire, "type": "refresh"}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_refresh_token(token: str) -> int:
    """검증 실패 시 JWTError raise."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "refresh":
        raise JWTError("refresh 토큰이 아닙니다.")
    return int(payload["sub"])


# ── DB 조작 ───────────────────────────────────────────────────────────────────

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalars().first()


async def create_user(
    db: AsyncSession,
    email: str,
    password: str,
    username: str,
    gender: Optional[str],
    birthDate: Optional[date],
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        username=username,
        gender=gender,
        birthdate=birthDate,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    user = await get_user_by_email(db, email)
    if user is None or not user.hashed_password:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def save_refresh_token(db: AsyncSession, user: User, token: str) -> None:
    user.refresh_token = token
    await db.commit()


async def clear_refresh_token(db: AsyncSession, user: User) -> None:
    user.refresh_token = None
    await db.commit()


# ── 소셜 로그인 ───────────────────────────────────────────────────────────────

async def exchange_social_code(
    db: AsyncSession, provider: str, code: str
) -> User:
    """
    소셜 로그인 코드를 유저 정보로 교환한다.
    실제 구현 시 provider별 OAuth API 호출 필요.
    """
    # TODO: provider별 실제 OAuth 코드 교환 구현
    #   kakao  → https://kauth.kakao.com/oauth/token
    #   google → https://oauth2.googleapis.com/token
    #   apple  → https://appleid.apple.com/auth/token
    raise NotImplementedError(f"소셜 로그인 미구현: provider={provider}")


# ── 비밀번호 재설정 ───────────────────────────────────────────────────────────

async def create_pw_reset_token(db: AsyncSession, user: User) -> str:
    token = secrets.token_urlsafe(32)
    user.pw_reset_token = token
    user.pw_reset_expires = datetime.now(timezone.utc) + timedelta(minutes=PW_RESET_EXPIRE_MINUTES)
    await db.commit()
    return token


def _build_reset_email(to: str, reset_link: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "[Chatda] 비밀번호 재설정 안내"
    msg["From"] = SMTP_SENDER
    msg["To"] = to

    text_body = (
        f"안녕하세요, Chatda입니다.\n\n"
        f"아래 링크를 클릭하여 비밀번호를 재설정하세요 (30분 이내 유효):\n\n"
        f"{reset_link}\n\n"
        f"본인이 요청하지 않은 경우 이 이메일을 무시하세요."
    )
    html_body = f"""
    <p>안녕하세요, <strong>Chatda</strong>입니다.</p>
    <p>아래 버튼을 클릭하여 비밀번호를 재설정하세요. (30분 이내 유효)</p>
    <p>
      <a href="{reset_link}"
         style="display:inline-block;padding:12px 24px;background:#4F46E5;
                color:#fff;border-radius:6px;text-decoration:none;font-weight:bold;">
        비밀번호 재설정
      </a>
    </p>
    <p style="color:#6B7280;font-size:13px;">
      본인이 요청하지 않은 경우 이 이메일을 무시하세요.
    </p>
    """
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _send_smtp(to: str, msg: MIMEMultipart) -> None:
    """smtplib으로 STARTTLS 메일 발송 (blocking — to_thread로 호출)."""
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.sendmail(SMTP_SENDER, to, msg.as_string())


async def send_pw_reset_email(email: str, token: str) -> None:
    """비밀번호 재설정 링크를 SMTP로 발송한다."""
    reset_link = f"{PW_RESET_BASE_URL}?token={token}"

    if not SMTP_USER or not SMTP_PASSWORD:
        # SMTP 미설정 시 로그만 출력 (개발 환경)
        logger.warning("[PWReset] SMTP 미설정 — 이메일 발송 생략. 링크=%s", reset_link)
        return

    msg = _build_reset_email(email, reset_link)
    try:
        await asyncio.to_thread(_send_smtp, email, msg)
        logger.info("[PWReset] 이메일 발송 완료: %s", email)
    except Exception as exc:
        logger.error("[PWReset] 이메일 발송 실패: %s — %s", email, exc)
        raise


async def reset_password(db: AsyncSession, token: str, new_password: str) -> Optional[User]:
    """
    토큰을 검증하고 비밀번호를 변경한다.
    토큰 만료/불일치 시 None 반환.
    """
    result = await db.execute(select(User).where(User.pw_reset_token == token))
    user = result.scalars().first()

    if user is None:
        return None

    now = datetime.now(timezone.utc)
    expires = user.pw_reset_expires
    if expires is None or (expires.tzinfo is None and expires.replace(tzinfo=timezone.utc) < now) or \
       (expires.tzinfo is not None and expires < now):
        return None

    user.hashed_password = hash_password(new_password)
    user.pw_reset_token = None
    user.pw_reset_expires = None
    user.refresh_token = None   # 기존 세션 무효화
    await db.commit()
    await db.refresh(user)
    return user
