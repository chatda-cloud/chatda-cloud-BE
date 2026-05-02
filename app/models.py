from __future__ import annotations

import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Enum, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db import Base


class ItemStatus(str, enum.Enum):
    LOST = "LOST"
    FOUND = "FOUND"
    MATCHED = "MATCHED"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_users_user_id"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(30), nullable=False)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fcm_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    birthdate: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    profile_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    pw_reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pw_reset_expires: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    items: Mapped[list[Item]] = relationship("Item", back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} user_id={self.user_id!r}>"


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ItemStatus] = mapped_column(Enum(ItemStatus, name="item_status"), nullable=False, default=ItemStatus.LOST)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="items")
    lost_item: Mapped[LostItem | None] = relationship("LostItem", back_populates="item", uselist=False, cascade="all, delete-orphan")
    found_item: Mapped[FoundItem | None] = relationship("FoundItem", back_populates="item", uselist=False, cascade="all, delete-orphan")
    lost_matches: Mapped[list[Match]] = relationship("Match", foreign_keys="Match.lost_item_id", back_populates="lost_item")
    found_matches: Mapped[list[Match]] = relationship("Match", foreign_keys="Match.found_item_id", back_populates="found_item")

    def __repr__(self) -> str:
        return f"<Item id={self.id} category={self.category!r} status={self.status}>"


class LostItem(Base):
    __tablename__ = "lost_items"

    item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)        # 사용자 입력 물건 이름
    date_start: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    date_end: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    features: Mapped[list | None] = mapped_column(JSONB, nullable=True)        # AI 추출 특징 (ai_tags → features)
    item_vector: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)

    item: Mapped[Item] = relationship("Item", back_populates="lost_item")

    def __repr__(self) -> str:
        return f"<LostItem item_id={self.item_id} item_name={self.item_name!r}>"


class FoundItem(Base):
    __tablename__ = "found_items"

    item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)        # 사용자 입력 물건 이름
    found_date: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    location: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    features: Mapped[list | None] = mapped_column(JSONB, nullable=True)        # AI 추출 특징 (ai_tags → features)
    item_vector: Mapped[list[float] | None] = mapped_column(Vector(512), nullable=True)

    item: Mapped[Item] = relationship("Item", back_populates="found_item")

    def __repr__(self) -> str:
        return f"<FoundItem item_id={self.item_id} item_name={self.item_name!r}>"


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("lost_item_id", "found_item_id", name="uq_matches_pair"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lost_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    found_item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    matched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    lost_item: Mapped[Item] = relationship("Item", foreign_keys=[lost_item_id], back_populates="lost_matches")
    found_item: Mapped[Item] = relationship("Item", foreign_keys=[found_item_id], back_populates="found_matches")

    def __repr__(self) -> str:
        return f"<Match id={self.id} lost={self.lost_item_id} found={self.found_item_id} score={self.similarity_score:.2f}>"