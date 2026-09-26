"""Server-controlled accounting, idempotency, bounded per-session work."""
import logging
import math
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from .jokes import JOKES, pick_joke
from .models import AchievementUnlock, BatchReceipt, GameSession, Player, utc_now
from .schemas import BatchIn

log = logging.getLogger(__name__)
SESSION_MAX_AGE = timedelta(minutes=5)
# Max touches for first batch: 4; +18/s across the whole session; each batch +4 burst.
REWARD_RATE = 18
REWARD_BURST = 4
MAX_SESSION_REWARD = 2500
ACHIEVEMENTS = {
    'FIRST_TOUCH': {'name': 'Первый контакт', 'description': 'Трава теперь знает о вас.', 'icon': '🌱'},
    'GRASS_100': {'name': 'Ладонь природы', 'description': '100 виртуальных контактов.', 'icon': '🍀'},
    'GRASS_1000': {'name': 'Senior Grass Engineer', 'description': 'Тысяча поглаживаний. В резюме уже можно писать.', 'icon': '👑'},
    'FIRST_SESSION': {'name': 'Вышел из дома.exe', 'description': 'Успешно закрыл первую сессию.', 'icon': '🏡'},
    'COMBO_25': {'name': 'Травяное цунами', 'description': 'Комбо в 25 касаний за один заход.', 'icon': '🌊'},
}


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def level_for_xp(xp: int) -> int:
    # Level 2 -> 100 XP; level 3 -> 300 XP; level 4 -> 600 XP.
    return max(1, (1 + math.isqrt(1 + 8 * (xp // 100))) // 2) if xp >= 100 else 1


def xp_for_level(level: int) -> int:
    return 50 * (level - 1) * level


def unlocked(db: Session, player_id: int) -> list[str]:
    return list(db.scalars(select(AchievementUnlock.code).where(AchievementUnlock.player_id == player_id)))


def public_player(db: Session, player: Player) -> dict:
    codes = unlocked(db, player.id)
    lvl = level_for_xp(player.xp)
    return {'id': str(player.id), 'first_name': player.first_name, 'username': player.username,
            'total_touches': player.total_touches, 'xp': player.xp, 'level': lvl,
            'current_level_xp': xp_for_level(lvl), 'next_level_xp': xp_for_level(lvl+1),
            'sessions_completed': player.sessions_completed, 'achievements': codes}


def session_view(session: GameSession | None) -> dict | None:
    if session is None:
        return None
    return {'id': session.id, 'started_at': aware(session.started_at).isoformat(),
            'awarded': session.awarded, 'last_seq': session.last_seq,
            'finished': session.finished_at is not None}


def active_session(db: Session, player_id: int, now: datetime | None = None) -> GameSession | None:
    now = now or utc_now()
    candidate = db.scalar(select(GameSession).where(GameSession.player_id == player_id,
                         GameSession.finished_at.is_(None)).order_by(GameSession.started_at.desc()).limit(1))
    if candidate and now - aware(candidate.started_at) < SESSION_MAX_AGE:
        return candidate
    return None


def start_session(db: Session, player: Player, now: datetime | None = None) -> tuple[GameSession, str]:
    now = now or utc_now()
    # Serializes concurrent start calls on PostgreSQL.
    db.scalar(select(Player).where(Player.id == player.id).with_for_update())
    existing = active_session(db, player.id, now)
    if existing:
        return existing, ''
    session = GameSession(player_id=player.id, started_at=now, last_award_at=now)
    db.add(session)
    db.flush()  # SQLAlchemy assigns the default UUID on INSERT.
    _, joke, recent = pick_joke('start', player.recent_jokes or [], session.id)
    player.recent_jokes = recent
    db.commit()
    db.refresh(session)
    return session, joke


def get_achievement(db: Session, player_id: int, code: str, new: list[str]) -> None:
    if code in unlocked(db, player_id):
        return
    db.add(AchievementUnlock(player_id=player_id, code=code))
    db.flush()
    new.append(code)


def apply_batch(db: Session, player_id: int, session_id: str, batch: BatchIn,
                now: datetime | None = None) -> dict:
    now = now or utc_now()
    # Lock PLAYER first consistently; serializes updates across tabs and sessions.
    player = db.scalar(select(Player).where(Player.id == player_id).with_for_update())
    if not player:
        raise LookupError('Player not found')
    session = db.scalar(select(GameSession).where(GameSession.id == session_id,
                        GameSession.player_id == player_id).with_for_update())
    if not session:
        raise LookupError('Game session not found')
    prev = db.scalar(select(BatchReceipt).where(BatchReceipt.session_id == session_id,
                     BatchReceipt.batch_id == str(batch.batch_id)))
    if prev:
        # Idempotent: never grant a reward twice; report original batch result.
        return _receipt_response(prev, player, session, db, duplicate=True)
    if session.finished_at is not None or now - aware(session.started_at) > SESSION_MAX_AGE:
        raise ValueError('Session expired or finished')
    if batch.seq != session.last_seq + 1:
        raise ValueError('Out-of-order batch; please sync your game')
    elapsed = max(0, (now - aware(session.started_at)).total_seconds())
    gap = max(0, (now - aware(session.last_award_at)).total_seconds())
    remaining_total = max(0, REWARD_BURST + int(elapsed * REWARD_RATE) - session.awarded)
    remaining_batch = REWARD_BURST + int(gap * REWARD_RATE)
    granted = max(0, min(batch.touches, remaining_total, remaining_batch, MAX_SESSION_REWARD - session.awarded))
    session.last_seq = batch.seq
    session.last_award_at = now
    session.awarded += granted
    player.total_touches += granted
    player.xp += granted
    new: list[str] = []
    if player.total_touches >= 1:
        get_achievement(db, player.id, 'FIRST_TOUCH', new)
    if player.total_touches >= 100:
        get_achievement(db, player.id, 'GRASS_100', new)
    if player.total_touches >= 1000:
        get_achievement(db, player.id, 'GRASS_1000', new)
    # Combo is client-observed and not provable. Require 25 *server-accepted* touches
    # in the session before permitting this cosmetic achievement.
    if batch.peak_combo >= 25 and session.awarded >= 25:
        get_achievement(db, player.id, 'COMBO_25', new)
    joke_kind = ('achievement' if new else 'combo' if batch.peak_combo >= 15 else
                 'milestone' if player.total_touches and player.total_touches % 100 <= granted else 'touch')
    joke_id, _, recent = pick_joke(joke_kind, player.recent_jokes or [], f'{session_id}:{batch.seq}')
    player.recent_jokes = recent
    receipt = BatchReceipt(player_id=player_id, session_id=session_id,
                           batch_id=str(batch.batch_id), seq=batch.seq, requested=batch.touches,
                           awarded=granted, joke_id=joke_id, new_achievements=new)
    db.add(receipt)
    if granted < batch.touches:
        session.flags += 1
        log.warning('Reward clamped player=%s session=%s requested=%s granted=%s',
                    player_id, session_id, batch.touches, granted)
    db.commit()
    return _receipt_response(receipt, player, session, db)


def _receipt_response(receipt: BatchReceipt, player: Player, session: GameSession,
                      db: Session, duplicate: bool = False) -> dict:
    return {'batch_id': receipt.batch_id, 'seq': receipt.seq,
            'granted': receipt.awarded, 'requested': receipt.requested,
            'total_touches': player.total_touches, 'xp': player.xp,
            'level': level_for_xp(player.xp), 'session_touches': session.awarded,
            'joke': JOKES[receipt.joke_id][1] if receipt.joke_id else '',
            'new_achievements': receipt.new_achievements or [], 'duplicate': duplicate}


def finish_session(db: Session, player_id: int, session_id: str,
                   now: datetime | None = None) -> dict:
    now = now or utc_now()
    player = db.scalar(select(Player).where(Player.id == player_id).with_for_update())
    session = db.scalar(select(GameSession).where(GameSession.id == session_id,
                        GameSession.player_id == player_id).with_for_update())
    if not player or not session:
        raise LookupError('Session not found')
    new: list[str] = []
    if session.finished_at is None:
        session.finished_at = now
        if session.awarded > 0:
            player.sessions_completed += 1
            get_achievement(db, player.id, 'FIRST_SESSION', new)
        _, joke, recent = pick_joke('finish', player.recent_jokes or [], session.id)
        player.recent_jokes = recent
        db.commit()
    else:
        joke = 'Результат уже сохранен. Трава все помнит.'
    return {'session': session_view(session), 'player': public_player(db, player),
            'new_achievements': new, 'joke': joke}
