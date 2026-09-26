"""Minimal authoritative game data; no unverified client-supplied scores."""
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, Index
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
    selected_location: Mapped[str] = mapped_column(String(40), default='windowsill', nullable=False)
    selected_grass: Mapped[str] = mapped_column(String(40), default='meadow', nullable=False)
    activity_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    show_public_profile: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    referrer_id: Mapped[int | None] = mapped_column(BigInteger().with_variant(Integer, 'sqlite'),
        ForeignKey('players.id', ondelete='SET NULL'), index=True, nullable=True)
    recent_jokes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sessions: Mapped[list['GameSession']] = relationship(back_populates='player')


class GameSession(Base):
    __tablename__ = 'game_sessions'
    __table_args__ = (Index('ix_session_player_finished', 'player_id', 'finished_at'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    player_id: Mapped[int] = mapped_column(ForeignKey('players.id', ondelete='CASCADE'), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_award_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    awarded: Mapped[int] = mapped_column(Integer, default=0)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    flags: Mapped[int] = mapped_column(Integer, default=0)
    species_awarded: Mapped[str | None] = mapped_column(String(40), nullable=True)
    location_code: Mapped[str] = mapped_column(String(40), default='windowsill', nullable=False)
    player: Mapped[Player] = relationship(back_populates='sessions')


class BatchReceipt(Base):
    __tablename__ = 'batch_receipts'
    __table_args__ = (
        UniqueConstraint('session_id', 'batch_id', name='uq_batch_session'),
        Index('ix_receipt_player_created', 'player_id', 'created_at'),
        Index('ix_receipts_created_at', 'created_at'),
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


class GrassUnlock(Base):
    __tablename__ = 'grass_unlocks'
    __table_args__ = (UniqueConstraint('player_id', 'species_code', name='uq_player_grass'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey('players.id', ondelete='CASCADE'), index=True)
    species_code: Mapped[str] = mapped_column(String(40), nullable=False)
    copies: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DailyClaim(Base):
    __tablename__ = 'daily_claims'
    __table_args__ = (UniqueConstraint('player_id', 'day', 'quest_code', name='uq_player_day_quest'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey('players.id', ondelete='CASCADE'), index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    quest_code: Mapped[str] = mapped_column(String(40), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WeeklyClaim(Base):
    __tablename__ = 'weekly_claims'
    __table_args__ = (UniqueConstraint('player_id', 'week_start', 'quest_code',
                                      name='uq_player_week_quest'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey('players.id', ondelete='CASCADE'), index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    quest_code: Mapped[str] = mapped_column(String(40), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FieldMission(Base):
    __tablename__ = 'field_missions'
    __table_args__ = (UniqueConstraint('player_id', 'day', name='uq_player_field_day'),
                      Index('ix_field_missions_day', 'day'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey('players.id', ondelete='CASCADE'), index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    location_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    xp: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
