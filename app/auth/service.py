"""auth 비즈니스 로직."""
import asyncio
import logging
import secrets
import smtplib

import httpx
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
    KAKAO_CLIENT_ID,
    KAKAO_REDIRECT_URI,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_REDIRECT_URI,
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


# ── 비밀번호 ──────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────
def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "type": "refresh"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_refresh_token(token: str) -> int:
    """검증 실패 시 JWTError raise."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "refresh":
        raise JWTError("refresh 토큰이 아닙니다.")
    return int(payload["sub"])


# ── DB 조작 ───────────────────────────────────────────────
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
        user_id=email.split("@")[0],   # user_id는 이메일 앞부분으로 자동 설정 (필요시 변경)
        password=hash_password(password),
        email=email,
        username=username,
        gender=gender,
        birthdate=birthDate,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    user = await get_user_by_email(db, email)
    if user is None or not user.password:
        return None
    if not verify_password(password, user.password):
        return None
    return user


async def save_refresh_token(db: AsyncSession, user: User, token: str) -> None:
    user.refresh_token = token
    await db.flush()


async def clear_refresh_token(db: AsyncSession, user: User) -> None:
    user.refresh_token = None
    await db.flush()


# ── 소셜 로그인 ───────────────────────────────────────────
async def exchange_social_code(db: AsyncSession, provider: str, code: str) -> User:
    if provider == "kakao":
        return await _exchange_kakao(db, code)
    if provider == "google":
        return await _exchange_google(db, code)
    if provider == "naver":
        return await _exchange_naver(db, code)
    raise NotImplementedError(f"소셜 로그인 미구현: provider={provider}")


async def _exchange_kakao(db: AsyncSession, code: str) -> User:
    async with httpx.AsyncClient() as client:
        # 1. 인가 코드 → 액세스 토큰
        token_res = await client.post(
            "https://kauth.kakao.com/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": KAKAO_CLIENT_ID,
                "redirect_uri": KAKAO_REDIRECT_URI,
                "code": code,
            },
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        # 2. 액세스 토큰 → 유저 정보
        user_res = await client.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_res.raise_for_status()
        user_data = user_res.json()

    kakao_id = str(user_data["id"])
    profile = user_data.get("kakao_account", {}).get("profile", {})
    nickname = profile.get("nickname") or f"user_{kakao_id[-6:]}"
    profile_image = profile.get("profile_image_url")

    # 3. 기존 유저 조회 → 없으면 자동 가입
    result = await db.execute(
        select(User).where(User.social_id == kakao_id, User.provider == "kakao")
    )
    user = result.scalars().first()

    if user is None:
        user = User(
            user_id=f"kakao_{kakao_id}",
            email=f"kakao_{kakao_id}@chatda.social",
            password=None,
            username=nickname,
            social_id=kakao_id,
            provider="kakao",
            profile_image_url=profile_image,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    return user


async def _exchange_google(db: AsyncSession, code: str) -> User:
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "authorization_code",
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "code": code,
            },
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        user_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_res.raise_for_status()
        user_data = user_res.json()

    google_id = str(user_data["id"])
    email = user_data.get("email") or f"google_{google_id}@chatda.social"
    name = user_data.get("name") or f"user_{google_id[-6:]}"
    profile_image = user_data.get("picture")

    result = await db.execute(
        select(User).where(User.social_id == google_id, User.provider == "google")
    )
    user = result.scalars().first()

    if user is None:
        user = User(
            user_id=f"google_{google_id}",
            email=email,
            password=None,
            username=name,
            social_id=google_id,
            provider="google",
            profile_image_url=profile_image,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    return user


async def _exchange_naver(db: AsyncSession, code: str) -> User:
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://nid.naver.com/oauth2.0/token",
            params={
                "grant_type": "authorization_code",
                "client_id": NAVER_CLIENT_ID,
                "client_secret": NAVER_CLIENT_SECRET,
                "redirect_uri": NAVER_REDIRECT_URI,
                "code": code,
                "state": "chatda",
            },
        )
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]

        user_res = await client.get(
            "https://openapi.naver.com/v1/nid/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_res.raise_for_status()
        user_data = user_res.json().get("response", {})

    naver_id = str(user_data["id"])
    email = user_data.get("email") or f"naver_{naver_id}@chatda.social"
    name = user_data.get("name") or user_data.get("nickname") or f"user_{naver_id[-6:]}"
    profile_image = user_data.get("profile_image")

    result = await db.execute(
        select(User).where(User.social_id == naver_id, User.provider == "naver")
    )
    user = result.scalars().first()

    if user is None:
        user = User(
            user_id=f"naver_{naver_id}",
            email=email,
            password=None,
            username=name,
            social_id=naver_id,
            provider="naver",
            profile_image_url=profile_image,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)

    return user


# ── 비밀번호 재설정 ───────────────────────────────────────
async def create_pw_reset_token(db: AsyncSession, user: User) -> str:
    token = secrets.token_urlsafe(32)
    user.pw_reset_token = token
    user.pw_reset_expires = datetime.now(timezone.utc) + timedelta(minutes=PW_RESET_EXPIRE_MINUTES)
    await db.flush()
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
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.sendmail(SMTP_SENDER, to, msg.as_string())


async def send_pw_reset_email(email: str, token: str) -> None:
    reset_link = f"{PW_RESET_BASE_URL}?token={token}"

    if not SMTP_USER or not SMTP_PASSWORD:
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
    result = await db.execute(select(User).where(User.pw_reset_token == token))
    user = result.scalars().first()

    if user is None:
        return None

    now = datetime.now(timezone.utc)
    expires = user.pw_reset_expires
    if expires is None:
        return None
    # timezone 정보 없는 경우 UTC로 처리
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        return None

    user.password = hash_password(new_password)
    user.pw_reset_token = None
    user.pw_reset_expires = None
    user.refresh_token = None   # 기존 세션 무효화
    await db.flush()
    await db.refresh(user)
    return user