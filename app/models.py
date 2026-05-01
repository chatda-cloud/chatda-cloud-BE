"""SQLAlchemy 모델.
각 담당자는 이 파일을 import 하여 사용.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship

try:
    from pgvector.sqlalchemy import Vector
    _VECTOR_AVAILABLE = True
except ImportError:
    _VECTOR_AVAILABLE = False


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id                = Column(Integer, primary_key=True, index=True)
    email             = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password   = Column(String(255), nullable=True)   # 소셜 로그인은 null 허용
    username          = Column(String(50), nullable=False)
    gender            = Column(String(10), nullable=True)    # MALE | FEMALE | OTHER
    birthdate         = Column(Date, nullable=True)
    profile_image_url = Column(Text, nullable=True)
    refresh_token     = Column(Text, nullable=True)          # 로그인 시 저장, 로그아웃 시 null
    pw_reset_token    = Column(String(255), nullable=True)   # 비밀번호 재설정 토큰
    pw_reset_expires  = Column(DateTime(timezone=True), nullable=True)
    is_active         = Column(Boolean, default=True, nullable=False)
    created_at        = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    items   = relationship("Item", back_populates="owner", lazy="select")
    matches = relationship("Match", back_populates="user", lazy="select")


class Item(Base):
    __tablename__ = "items"

    id         = Column(Integer, primary_key=True, index=True)
    owner_id   = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    item_type  = Column(String(10), nullable=False)          # LOST | FOUND
    category   = Column(String(50))
    raw_text   = Column(Text)
    image_url  = Column(Text)
    ai_tags    = Column(JSONB)
    status     = Column(String(20), default="PENDING", nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    if _VECTOR_AVAILABLE:
        item_vector = Column(Vector(512))

    owner = relationship("User", back_populates="items", lazy="select")


class Match(Base):
    __tablename__ = "matches"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    lost_item_id  = Column(Integer, ForeignKey("items.id"), nullable=False)
    found_item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    similarity    = Column(Integer, nullable=False)           # 0~100
    status        = Column(String(20), default="PENDING", nullable=False)
    created_at    = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="matches", lazy="select")
