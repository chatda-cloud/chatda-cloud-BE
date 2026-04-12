"""
auth 라우터

  POST   /api/auth/signup           → 회원가입
  POST   /api/auth/signin           → 일반 로그인
  DELETE /api/auth/logout           → 로그아웃
  POST   /api/auth/exchange         → 소셜 로그인 코드 교환
  POST   /api/auth/token/reissue    → Access 토큰 재발급
  POST   /api/auth/pwreset/request  → 비밀번호 재설정 링크 요청
  POST   /api/auth/pwreset/confirm  → 비밀번호 재설정 확인
"""
from jose import JWTError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import get_current_user
from app.models import User
from app.auth.schema import (
    PwResetConfirmBody,
    PwResetRequestBody,
    SigninRequest,
    SignupRequest,
    SocialExchangeRequest,
    TokenReissueRequest,
    TokenResponse,
)
from app.auth.service import (
    authenticate_user,
    clear_refresh_token,
    create_access_token,
    create_pw_reset_token,
    create_refresh_token,
    create_user,
    decode_refresh_token,
    exchange_social_code,
    get_user_by_email,
    get_user_by_id,
    reset_password,
    save_refresh_token,
    send_pw_reset_email,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_response(user: User, access_token: str, refresh_token: str) -> dict:
    return TokenResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        id=user.id,
        username=user.username,
        email=user.email,
    ).model_dump()


# ── 회원가입 ──────────────────────────────────────────────────────────────────

@router.post("/signup", status_code=201)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    if await get_user_by_email(db, body.email):
        raise HTTPException(status_code=409, detail={
            "success": False, "code": 409,
            "message": "이미 사용 중인 이메일입니다.", "data": None,
        })

    user = await create_user(
        db, body.email, body.password, body.username, body.gender, body.birthDate
    )
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    await save_refresh_token(db, user, refresh)

    return {"success": True, "code": 201, "message": "회원가입 성공",
            "data": _token_response(user, access, refresh)}


# ── 일반 로그인 ───────────────────────────────────────────────────────────────

@router.post("/signin")
async def signin(body: SigninRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail={
            "success": False, "code": 401,
            "message": "이메일 또는 비밀번호가 올바르지 않습니다.", "data": None,
        })

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    await save_refresh_token(db, user, refresh)

    return _token_response(user, access, refresh)


# ── 로그아웃 ──────────────────────────────────────────────────────────────────

@router.delete("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 서버: DB의 refresh_token을 null로 설정 (재발급 차단)
    # [프론트엔드 필수] 응답 수신 후 로컬에 저장된 Access Token과 Refresh Token을
    # 반드시 삭제해야 합니다. Access Token은 서버에서 즉시 무효화되지 않으므로
    # (JWT stateless 구조), 클라이언트가 직접 폐기해야 세션이 완전히 종료됩니다.
    await clear_refresh_token(db, current_user)
    return {"message": "로그아웃 완료"}


# ── 소셜 로그인 코드 교환 ──────────────────────────────────────────────────────

@router.post("/exchange")
async def social_exchange(body: SocialExchangeRequest, db: AsyncSession = Depends(get_db)):
    if body.provider not in ("kakao", "google", "apple"):
        raise HTTPException(status_code=400, detail={
            "success": False, "code": 400,
            "message": "지원하지 않는 provider입니다. (kakao | google | apple)", "data": None,
        })

    try:
        user = await exchange_social_code(db, body.provider, body.code)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail={
            "success": False, "code": 501, "message": str(e), "data": None,
        })

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    await save_refresh_token(db, user, refresh)

    return {"success": True, "code": 200, "message": "소셜 로그인 성공",
            "data": _token_response(user, access, refresh)}


# ── Access 토큰 재발급 ────────────────────────────────────────────────────────

@router.post("/token/reissue")
async def token_reissue(body: TokenReissueRequest, db: AsyncSession = Depends(get_db)):
    try:
        user_id = decode_refresh_token(body.refreshToken)
    except JWTError:
        raise HTTPException(status_code=401, detail={
            "success": False, "code": 401,
            "message": "유효하지 않거나 만료된 Refresh 토큰입니다.", "data": None,
        })

    user = await get_user_by_id(db, user_id)
    if user is None or user.refresh_token != body.refreshToken:
        raise HTTPException(status_code=401, detail={
            "success": False, "code": 401,
            "message": "Refresh 토큰이 일치하지 않습니다. 다시 로그인해주세요.", "data": None,
        })

    new_access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    await save_refresh_token(db, user, new_refresh)

    return {"success": True, "code": 200, "message": "토큰 재발급 성공",
            "data": {"accessToken": new_access, "refreshToken": new_refresh, "tokenType": "bearer"}}


# ── 비밀번호 재설정 링크 요청 ─────────────────────────────────────────────────

@router.post("/pwreset/request")
async def pw_reset_request(body: PwResetRequestBody, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, body.email)
    # 보안: 유저 존재 여부와 무관하게 동일 응답 (이메일 열거 공격 방지)
    if user is not None:
        token = await create_pw_reset_token(db, user)
        await send_pw_reset_email(user.email, token)

    return {"success": True, "code": 200,
            "message": "비밀번호 재설정 링크를 이메일로 발송했습니다.", "data": None}


# ── 비밀번호 재설정 확인 ──────────────────────────────────────────────────────

@router.post("/pwreset/confirm", status_code=204)
async def pw_reset_confirm(body: PwResetConfirmBody, db: AsyncSession = Depends(get_db)):
    user = await reset_password(db, body.token, body.newPassword)
    if user is None:
        raise HTTPException(status_code=400, detail={
            "success": False, "code": 400,
            "message": "유효하지 않거나 만료된 토큰입니다.", "data": None,
        })

    return Response(status_code=204)
