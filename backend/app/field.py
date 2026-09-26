"""A rotating personal field assignment: immutable for each UTC day, fully server-verified."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AchievementUnlock, BatchReceipt, FieldMission, GameSession, Player, utc_now
from .progress import utc_period
from .weather import utc_weather
from .world import LOCATIONS, can_visit

MISSIONS = {
    'touch_90': {'name': 'Контрольная закупка травы', 'description': '90 подтвержденных касаний за сегодня.',
                 'target': 90, 'xp': 80, 'icon': '🧪', 'kind': 'touches'},
    'two_outings': {'name': 'Двойной выход в интернет', 'description': 'Две завершенные сессии минимум с 25 касаниями каждая.',
                    'target': 2, 'xp': 75, 'icon': '🥾', 'kind': 'sessions'},
    'strong_session': {'name': 'Нежность промышленного масштаба', 'description': 'Одна сессия с 70 принятыми касаниями.',
                       'target': 70, 'xp': 90, 'icon': '💚', 'kind': 'strong'},
    'home_visit': {'name': 'Инспекция родного газона', 'description': 'Заверши сессию с 45 касаниями на указанной лужайке.',
                   'target': 1, 'xp': 80, 'icon': '📋', 'kind': 'location'},
    'foreign_visit': {'name': 'Дипломатическая миссия к соседям', 'description': 'Заверши сессию с 40 касаниями в указанной новой локации.',
                      'target': 1, 'xp': 115, 'icon': '🛰️', 'kind': 'travel'},
}


def _mission_for_today(db: Session, player: Player, now: datetime) -> FieldMission:
    day = now.astimezone(timezone.utc).date()
    found = db.scalar(select(FieldMission).where(FieldMission.player_id == player.id, FieldMission.day == day))
    if found:
        return found
    # Callers lock the player row *before* issuing a mission. It cannot reroll
    # when the player levels up, changes location or refreshes the Mini App.
    from .game import level_for_xp, unlocked
    unlocked_codes = set(unlocked(db, player.id))
    destinations = sorted(p.code for p in LOCATIONS.values() if can_visit(level_for_xp(player.xp), unlocked_codes, p))
    options = ['touch_90', 'two_outings', 'strong_session', 'home_visit']
    alternate = [p for p in destinations if p != player.selected_location]
    if alternate:
        options.append('foreign_visit')
    seed = sha256(f'field:v1:{player.id}:{day}'.encode()).digest()
    code = options[int.from_bytes(seed[:4], 'big') % len(options)]
    location = (alternate[int.from_bytes(seed[4:8], 'big') % len(alternate)] if code == 'foreign_visit'
                else player.selected_location if code == 'home_visit' else None)
    mission = FieldMission(player_id=player.id, day=day, code=code, location_code=location,
                           xp=MISSIONS[code]['xp'], created_at=now)
    db.add(mission)
    db.flush()
    return mission


def _progress(db: Session, player_id: int, mission: FieldMission, now: datetime) -> int:
    start, end = utc_period(now, 'day')
    if mission.code == 'touch_90':
        return int(db.scalar(select(func.coalesce(func.sum(BatchReceipt.awarded), 0)).where(
            BatchReceipt.player_id == player_id, BatchReceipt.created_at >= start,
            BatchReceipt.created_at < end)) or 0)
    done = (GameSession.player_id == player_id, GameSession.finished_at >= start,
            GameSession.finished_at < end)
    if mission.code == 'two_outings':
        return int(db.scalar(select(func.count()).select_from(GameSession).where(
            *done, GameSession.awarded >= 25)) or 0)
    if mission.code == 'strong_session':
        return int(db.scalar(select(func.coalesce(func.max(GameSession.awarded), 0)).where(*done)) or 0)
    if mission.code in {'home_visit', 'foreign_visit'}:
        threshold = 40 if mission.code == 'foreign_visit' else 45
        return int(bool(db.scalar(select(GameSession.id).where(
            *done, GameSession.started_at >= mission.created_at,
            GameSession.awarded >= threshold,
            GameSession.location_code == mission.location_code).limit(1))))
    raise ValueError('Unknown mission in database')


def _snapshot(db: Session, player: Player, mission: FieldMission, now: datetime) -> dict:
    spec = MISSIONS[mission.code]
    progress = min(spec['target'], _progress(db, player.id, mission, now))
    start, reset = utc_period(now, 'day')
    claimed_count = int(db.scalar(select(func.count()).select_from(FieldMission).where(
        FieldMission.player_id == player.id, FieldMission.claimed_at.is_not(None))) or 0)
    return {
        'date': start.date().isoformat(), 'resets_at': reset.isoformat(),
        'weather': utc_weather(player.selected_location, now),
        'missions_completed': claimed_count,
        'mission': {'code': mission.code, 'name': spec['name'], 'description': spec['description'],
                    'icon': spec['icon'], 'target': spec['target'], 'progress': progress, 'xp': mission.xp,
                    'location_code': mission.location_code,
                    'location_name': LOCATIONS[mission.location_code].name if mission.location_code else None,
                    'completed': progress >= spec['target'], 'claimed': mission.claimed_at is not None},
    }


def field_report(db: Session, player: Player, now: datetime | None = None) -> dict:
    now = now or utc_now()
    locked = db.scalar(select(Player).where(Player.id == player.id).with_for_update())
    mission = _mission_for_today(db, locked, now)
    result = _snapshot(db, locked, mission, now)
    db.commit()
    return result


def claim_field_mission(db: Session, player: Player, now: datetime | None = None) -> dict:
    now = now or utc_now()
    locked = db.scalar(select(Player).where(Player.id == player.id).with_for_update())
    mission = _mission_for_today(db, locked, now)
    if mission.claimed_at is not None:
        result = _snapshot(db, locked, mission, now)
        db.commit()
        return {'already_claimed': True, 'xp_granted': 0, 'new_achievements': [], 'report': result}
    spec = MISSIONS[mission.code]
    if _progress(db, locked.id, mission, now) < spec['target']:
        raise ValueError('Экспедиция еще не завершена')
    locked.xp += mission.xp
    mission.claimed_at = now
    from .game import get_achievement
    unlocked_now: list[str] = []
    claims = int(db.scalar(select(func.count()).select_from(FieldMission).where(
        FieldMission.player_id == locked.id, FieldMission.claimed_at.is_not(None))) or 0)
    if claims >= 3:
        get_achievement(db, locked.id, 'FIELD_SCOUT', unlocked_now)
    if claims >= 14:
        get_achievement(db, locked.id, 'FIELD_VETERAN', unlocked_now)
    result = _snapshot(db, locked, mission, now)
    db.commit()
    return {'already_claimed': False, 'xp_granted': mission.xp, 'new_achievements': unlocked_now,
            'report': result}
