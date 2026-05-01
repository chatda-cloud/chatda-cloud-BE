"""
공통 의존성
  get_current_user — JWT Bearer 토큰 검증 후 User 객체 반환.
  다른 라우터에서 Depends(get_current_user)로 사용.
"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import JWT_ALGORITHM, JWT_SECRET
from app.db import get_db
from app.models import User

_bearer = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Authorization: Bearer <token> 헤더를 검증하고 User를 반환.
    토큰 오류/만료/유저 없음 → 401
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise JWTError()
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail={
                "success": False,
                "code": 401,
                "message": "유효하지 않거나 만료된 토큰입니다.",
                "data": None,
            },
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={
                "success": False,
                "code": 401,
                "message": "존재하지 않는 사용자입니다.",
                "data": None,
            },
        )
    return user
