"""
매칭 서비스

최적화:
  - pgvector cosine_distance로 DB 레벨 ANN 탐색 → 상위 K개만 후보로
  - Python 레벨 정밀 스코어링 (feature booster + date score)
  - 매칭은 BackgroundTasks로 비동기 실행 (items/router.py에서 분리)

파이프라인:
  1. 하드 필터링 + pgvector 상위 K개 (SQL)
  2. 벡터 유사도 (70%) + Feature Booster (20%) + 날짜 소프트 스코어 (10%)
  3. 임계값 0.7 이상 → matches 저장 + SNS 푸시
"""
import asyncio
import logging
from datetime import datetime

import boto3
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import AWS_ACCESS_KEY_ID, AWS_REGION, AWS_SECRET_ACCESS_KEY, SNS_TOPIC_ARN, get_settings
from app.models import FoundItem, Item, ItemStatus, LostItem, Match

logger = logging.getLogger(__name__)
settings = get_settings()

MATCH_THRESHOLD = settings.MATCH_THRESHOLD
W_VECTOR = 0.7
W_FEATURE = 0.2
W_DATE = 0.1
TOP_K = 50  # pgvector로 뽑을 최대 후보 수


def _aws_client(service_name: str):
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs.update(
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
    return boto3.client(service_name, **kwargs)


# ── 유사도 계산 헬퍼 ───────────────────────────────────────
def _cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def _feature_score(features_a: list | None, features_b: list | None) -> float:
    if not features_a or not features_b:
        return 0.0
    set_a = set(f.lower() for f in features_a)
    set_b = set(f.lower() for f in features_b)
    return len(set_a & set_b) / max(len(set_a), len(set_b))


def _date_score(lost_start: datetime, lost_end: datetime, found_date: datetime) -> float:
    def to_naive(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

    lost_start = to_naive(lost_start)
    lost_end = to_naive(lost_end)
    found_date = to_naive(found_date)

    if lost_start <= found_date <= lost_end:
        return 1.0
    gap = min(
        abs((found_date - lost_start).days),
        abs((found_date - lost_end).days),
    )
    return max(0.0, 1.0 - (gap / 365))


def _final_score(lost: LostItem, found: FoundItem) -> float:
    if lost.item_vector is None or found.item_vector is None:
        return 0.0
    s_vector = _cosine_similarity(lost.item_vector, found.item_vector)
    s_feature = _feature_score(lost.features, found.features)
    s_date = _date_score(lost.date_start, lost.date_end, found.found_date)
    return (s_vector * W_VECTOR) + (s_feature * W_FEATURE) + (s_date * W_DATE)


# ── SNS 푸시 ──────────────────────────────────────────────
def _send_sns(message: str, subject: str) -> None:
    client = _aws_client("sns")
    client.publish(TopicArn=SNS_TOPIC_ARN, Message=message, Subject=subject)


async def _push_notification(score: float, lost_item_id: int, found_item_id: int) -> None:
    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _send_sns,
            f"분실물({lost_item_id})과 습득물({found_item_id})의 유사도가 {score:.0%}입니다.",
            "Chatda 분실물 매칭 알림",
        )
    except Exception:
        logger.exception("SNS 푸시 실패 (lost=%d, found=%d)", lost_item_id, found_item_id)


# ── 중복 체크 ─────────────────────────────────────────────
async def _match_exists(db: AsyncSession, lost_item_id: int, found_item_id: int) -> bool:
    result = await db.execute(
        select(Match).where(
            Match.lost_item_id == lost_item_id,
            Match.found_item_id == found_item_id,
        )
    )
    return result.scalars().first() is not None


# ── 매칭 저장 공통 헬퍼 ───────────────────────────────────
async def _save_matches(
    db: AsyncSession,
    pairs: list[tuple[LostItem, FoundItem]],
) -> list[Match]:
    created: list[Match] = []
    for lost, found in pairs:
        score = _final_score(lost, found)
        if score < MATCH_THRESHOLD:
            continue
        if await _match_exists(db, lost.item_id, found.item_id):
            continue

        match = Match(
            lost_item_id=lost.item_id,
            found_item_id=found.item_id,
            similarity_score=round(score, 4),
        )
        db.add(match)
        created.append(match)

        asyncio.create_task(
            _push_notification(score, lost.item_id, found.item_id)
        )

    await db.flush()
    return created


# ── 분실물 등록 시 → 기존 습득물 탐색 ────────────────────
async def run_matching_for_lost(
    db: AsyncSession,
    lost_item_id: int,
) -> list[Match]:
    result = await db.execute(
        select(LostItem)
        .options(joinedload(LostItem.item))
        .where(LostItem.item_id == lost_item_id)
    )
    lost = result.scalars().first()
    if not lost or lost.item.status == ItemStatus.MATCHED or lost.item_vector is None:
        logger.warning("run_matching_for_lost: 조건 미충족 (item_id=%d)", lost_item_id)
        return []

    # pgvector cosine_distance로 상위 TOP_K개만 조회
    candidates = await db.execute(
        select(FoundItem)
        .join(Item, Item.id == FoundItem.item_id)
        .options(joinedload(FoundItem.item))
        .where(
            Item.category == lost.item.category,
            Item.status != ItemStatus.MATCHED,
            FoundItem.item_vector.is_not(None),
        )
        .order_by(FoundItem.item_vector.cosine_distance(lost.item_vector))
        .limit(TOP_K)
    )
    found_list = candidates.scalars().all()

    pairs = [(lost, found) for found in found_list]
    matches = await _save_matches(db, pairs)

    logger.info(
        "run_matching_for_lost 완료: lost=%d, 후보=%d, 매칭=%d",
        lost_item_id, len(found_list), len(matches),
    )
    return matches


# ── 습득물 등록 시 → 기존 분실물 탐색 ────────────────────
async def run_matching_for_found(
    db: AsyncSession,
    found_item_id: int,
) -> list[Match]:
    result = await db.execute(
        select(FoundItem)
        .options(joinedload(FoundItem.item))
        .where(FoundItem.item_id == found_item_id)
    )
    found = result.scalars().first()
    if not found or found.item.status == ItemStatus.MATCHED or found.item_vector is None:
        logger.warning("run_matching_for_found: 조건 미충족 (item_id=%d)", found_item_id)
        return []

    # pgvector cosine_distance로 상위 TOP_K개만 조회
    candidates = await db.execute(
        select(LostItem)
        .join(Item, Item.id == LostItem.item_id)
        .options(joinedload(LostItem.item))
        .where(
            Item.category == found.item.category,
            Item.status != ItemStatus.MATCHED,
            LostItem.item_vector.is_not(None),
        )
        .order_by(LostItem.item_vector.cosine_distance(found.item_vector))
        .limit(TOP_K)
    )
    lost_list = candidates.scalars().all()

    pairs = [(lost, found) for lost in lost_list]
    matches = await _save_matches(db, pairs)

    logger.info(
        "run_matching_for_found 완료: found=%d, 후보=%d, 매칭=%d",
        found_item_id, len(lost_list), len(matches),
    )
    return matches


# ── 외부 진입점 ───────────────────────────────────────────
async def run_matching(
    db: AsyncSession,
    item_id: int,
    is_lost: bool = True,
) -> list[Match]:
    if is_lost:
        return await run_matching_for_lost(db, item_id)
    else:
        return await run_matching_for_found(db, item_id)


# ── 매칭 결과 조회 ────────────────────────────────────────
async def get_matches_by_lost_item(
    db: AsyncSession,
    lost_item_id: int,
) -> list[Match]:
    result = await db.execute(
        select(Match)
        .where(Match.lost_item_id == lost_item_id)
        .order_by(Match.similarity_score.desc())
    )
    return result.scalars().all()


# ── 매칭 확정 ─────────────────────────────────────────────
async def confirm_match(
    db: AsyncSession,
    match_id: int,
    user_id: int,
) -> Match | None:
    result = await db.execute(
        select(Match)
        .options(
            joinedload(Match.lost_item),
            joinedload(Match.found_item),
        )
        .where(Match.id == match_id)
    )
    match = result.scalars().first()
    if not match:
        return None

    if match.lost_item.user_id != user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail={
            "success": False, "code": 403,
            "message": "매칭 확정 권한이 없습니다.", "data": None,
        })

    match.is_confirmed = True
    match.matched_at = datetime.utcnow() 
    match.lost_item.status = ItemStatus.MATCHED
    match.found_item.status = ItemStatus.MATCHED

    await db.flush()
    return match
