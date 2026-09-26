"""Minimal authoritative game data; no unverified client-supplied scores."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Player(Base):
    __tablename__ = 'players'
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(120), default='Анонимный газон')
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_touches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sessions_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recent_jokes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sessions: Mapped[list['GameSession']] = relationship(back_populates='player')


class GameSession(Base):
    __tablename__ = 'game_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    player_id: Mapped[int] = mapped_column(ForeignKey('players.id', ondelete='CASCADE'), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_award_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    awarded: Mapped[int] = mapped_column(Integer, default=0)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    flags: Mapped[int] = mapped_column(Integer, default=0)
    player: Mapped[Player] = relationship(back_populates='sessions')


class BatchReceipt(Base):
    __tablename__ = 'batch_receipts'
    __table_args__ = (
        UniqueConstraint('session_id', 'batch_id', name='uq_batch_session'),
        Index('ix_receipt_player_created', 'player_id', 'created_at'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey('players.id', ondelete='CASCADE'))
    session_id: Mapped[str] = mapped_column(ForeignKey('game_sessions.id', ondelete='CASCADE'))
    batch_id: Mapped[str] = mapped_column(String(36))
    seq: Mapped[int] = mapped_column(Integer)
    requested: Mapped[int] = mapped_column(Integer)
    awarded: Mapped[int] = mapped_column(Integer)
    joke_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    new_achievements: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AchievementUnlock(Base):
    __tablename__ = 'achievement_unlocks'
    __table_args__ = (UniqueConstraint('player_id', 'code', name='uq_player_achievement'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey('players.id', ondelete='CASCADE'), index=True)
    code: Mapped[str] = mapped_column(String(50))
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
