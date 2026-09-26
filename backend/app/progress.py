"""World catalog, daily missions, bounded discoveries and UTC leaderboards."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AchievementUnlock, BatchReceipt, DailyClaim, GameSession, GrassUnlock, Player, WeeklyClaim, utc_now
from .world import LOCATIONS, RARITIES, SPECIES, can_visit, discover_species

WEEKLY_TASKS = {
    'WEEK_TOUCH_500': {'name': 'Уехать на дачу.exe', 'description': '500 принятых касаний за неделю.', 'target': 500, 'xp': 180, 'icon': '🏕️'},
    'WEEK_FOUR_SESSIONS': {'name': 'Социальный экстраверт', 'description': 'Четыре завершенные сессии за неделю.', 'target': 4, 'xp': 240, 'icon': '🪵'},
    'WEEK_TWO_FINDS': {'name': 'Корпоративный гербарий', 'description': 'Две находки травы за неделю.', 'target': 2, 'xp': 300, 'icon': '🔬'},
}

DAILY_TASKS = {
    'TOUCH_80': {'name': 'Выйти на улицу.exe', 'description': 'Потрогай 80 виртуальных травинок за день.', 'target': 80, 'xp': 35, 'icon': '👟'},
    'TWO_SESSIONS': {'name': 'Первый контакт с природой', 'description': 'Закончи две игровые сессии за день.', 'target': 2, 'xp': 50, 'icon': '☀️'},
    'FIND_GRASS': {'name': 'Ботаническая удача', 'description': 'Найди один вид травы за день.', 'target': 1, 'xp': 65, 'icon': '🍀'},
}


def utc_period(day: datetime, period: str) -> tuple[datetime, datetime]:
    today = day.astimezone(timezone.utc).date()
    if period == 'week':
        today = today - timedelta(days=today.weekday())
    start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    return start, start + timedelta(days=7 if period == 'week' else 1)


def collection(db: Session, player_id: int) -> dict[str, int]:
    rows = db.scalars(select(GrassUnlock).where(GrassUnlock.player_id == player_id)).all()
    return {item.species_code: item.copies for item in rows}


def world_snapshot(db: Session, player: Player, level: int, achievements: set[str]) -> dict:
    owned = collection(db, player.id)
    locations = []
    for place in LOCATIONS.values():
        available = can_visit(level, achievements, place)
        if place.secret and not available:
            continue
        locations.append({'code': place.code, 'name': place.name,
                          'description': place.description if available else 'Откроется на уровне ' + str(place.level),
                          'level': place.level, 'sky': place.sky, 'ground': place.ground,
                          'secret': place.secret, 'unlocked': available})
    return {'locations': locations, 'selected_location': player.selected_location,
            'selected_grass': player.selected_grass, 'rarities': RARITIES,
            'species': [dict(code=p.code, name=p.name, rarity=p.rarity, description=p.description,
                             color=p.color, motion=p.motion, copies=owned.get(p.code, 0),
                             unlocked=p.code == 'meadow' or p.code in owned) for p in SPECIES.values()]}


def select_location(db: Session, player: Player, code: str, level: int,
                    achievements: set[str]) -> str:
    location = LOCATIONS.get(code)
    if not location or not can_visit(level, achievements, location):
        raise ValueError('Эта лужайка пока закрыта')
    player.selected_location = code
    db.commit()
    return code


def select_grass(db: Session, player: Player, code: str) -> str:
    if code not in SPECIES:
        raise ValueError('Такого растения нет в гербарии')
    if code != 'meadow' and code not in collection(db, player.id):
        raise ValueError('Сначала найди эту траву в экспедиции')
    player.selected_grass = code
    db.commit()
    return code


def record_activity(player: Player, now: datetime) -> None:
    today = now.astimezone(timezone.utc).date()
    previous = player.last_active_date
    if previous == today:
        return
    if previous == today - timedelta(days=1):
        player.activity_streak += 1
    elif previous == today - timedelta(days=2):
        # One missed day is a soft grace day; the streak is preserved, not inflated.
        player.activity_streak = max(1, player.activity_streak)
    else:
        player.activity_streak = 1
    player.best_streak = max(player.best_streak, player.activity_streak)
    player.last_active_date = today


def find_grass(db: Session, player: Player, session: GameSession,
               now: datetime) -> dict | None:
    """At most three drops per UTC day. Retry of /finish cannot grant a second drop."""
    if session.awarded < 30 or session.species_awarded is not None:
        return None
    start, end = utc_period(now, 'day')
    daily_drops = db.scalar(select(func.count()).select_from(GameSession).where(
        GameSession.player_id == player.id, GameSession.finished_at >= start,
        GameSession.finished_at < end, GameSession.species_awarded.is_not(None))) or 0
    if daily_drops >= 3:
        return None
    species = discover_species(session.id)
    # Mythic Friday grass is genuinely Friday-only; a failed roll becomes the
    # other mythic plant instead of leaking an impossible collectible.
    if species.code == 'friday_success' and (now.astimezone(timezone.utc).weekday() != 4 or session.awarded < 100):
        species = SPECIES['cosmic_admin']
    existing = db.scalar(select(GrassUnlock).where(GrassUnlock.player_id == player.id,
                                                  GrassUnlock.species_code == species.code))
    if existing:
        existing.copies += 1
    else:
        db.add(GrassUnlock(player_id=player.id, species_code=species.code, copies=1,
                           first_found_at=now))
    session.species_awarded = species.code
    return {'code': species.code, 'name': species.name, 'rarity': species.rarity,
            'description': species.description, 'color': species.color,
            'duplicate': existing is not None}


def daily_snapshot(db: Session, player: Player, now: datetime | None = None) -> dict:
    now = now or utc_now()
    start, end = utc_period(now, 'day')
    day = start.date()
    touches = db.scalar(select(func.coalesce(func.sum(BatchReceipt.awarded), 0)).where(
        BatchReceipt.player_id == player.id, BatchReceipt.created_at >= start,
        BatchReceipt.created_at < end)) or 0
    sessions = db.scalar(select(func.count()).select_from(GameSession).where(
        GameSession.player_id == player.id, GameSession.finished_at >= start,
        GameSession.finished_at < end, GameSession.awarded > 0)) or 0
    plants = db.scalar(select(func.count()).select_from(GameSession).where(
        GameSession.player_id == player.id, GameSession.finished_at >= start,
        GameSession.finished_at < end, GameSession.species_awarded.is_not(None))) or 0
    claims = set(db.scalars(select(DailyClaim.quest_code).where(
        DailyClaim.player_id == player.id, DailyClaim.day == day)))
    amounts = {'TOUCH_80': int(touches), 'TWO_SESSIONS': int(sessions), 'FIND_GRASS': int(plants)}
    return {'date': day.isoformat(), 'resets_at': end.isoformat(), 'streak': player.activity_streak,
            'best_streak': player.best_streak,
            'quests': [dict(code=code, **meta, progress=min(amounts[code], meta['target']),
                            completed=amounts[code] >= meta['target'], claimed=code in claims)
                       for code, meta in DAILY_TASKS.items()]}


def claim_daily(db: Session, player: Player, code: str, now: datetime | None = None) -> dict:
    """Player row lock serializes claims across simultaneous tabs or processes."""
    now = now or utc_now()
    locked = db.scalar(select(Player).where(Player.id == player.id).with_for_update())
    if locked is None or code not in DAILY_TASKS:
        raise ValueError('Неизвестное ежедневное задание')
    day = now.astimezone(timezone.utc).date()
    already = db.scalar(select(DailyClaim).where(
        DailyClaim.player_id == player.id, DailyClaim.day == day, DailyClaim.quest_code == code))
    if already:
        return {'already_claimed': True, 'xp_granted': 0, 'xp': locked.xp,
                'daily': daily_snapshot(db, locked, now)}
    snapshot = daily_snapshot(db, locked, now)
    task = next(item for item in snapshot['quests'] if item['code'] == code)
    if not task['completed']:
        raise ValueError('Задание еще не выполнено')
    locked.xp += task['xp']
    db.add(DailyClaim(player_id=player.id, day=day, quest_code=code, claimed_at=now))
    db.commit()
    return {'already_claimed': False, 'xp_granted': task['xp'], 'xp': locked.xp,
            'daily': daily_snapshot(db, locked, now)}


def leaderboard(db: Session, period: str, now: datetime | None = None,
                limit: int = 20) -> dict:
    if period not in ('day', 'week'):
        raise ValueError('Unsupported leaderboard period')
    start, end = utc_period(now or utc_now(), period)
    # Only accepted receipts count. No user-provided XP or client-only observations.
    awarded = func.sum(BatchReceipt.awarded).label('touches')
    results = db.execute(select(Player.id, Player.first_name, Player.username, awarded)
        .join(BatchReceipt, BatchReceipt.player_id == Player.id)
        .where(BatchReceipt.created_at >= start, BatchReceipt.created_at < end,
               BatchReceipt.awarded > 0, Player.show_public_profile.is_(True))
        .group_by(Player.id, Player.first_name, Player.username)
        .order_by(awarded.desc(), Player.id.asc()).limit(limit)).all()
    return {'period': period, 'starts_at': start.isoformat(), 'ends_at': end.isoformat(),
            'leaders': [dict(rank=i, id=str(pid), first_name=name, username=username,
                             touches=int(score)) for i, (pid, name, username, score) in enumerate(results, 1)]}


def weekly_snapshot(db: Session, player: Player, now: datetime | None = None) -> dict:
    now = now or utc_now()
    start, end = utc_period(now, 'week')
    touches = db.scalar(select(func.coalesce(func.sum(BatchReceipt.awarded), 0)).where(
        BatchReceipt.player_id == player.id, BatchReceipt.created_at >= start,
        BatchReceipt.created_at < end)) or 0
    sessions = db.scalar(select(func.count()).select_from(GameSession).where(
        GameSession.player_id == player.id, GameSession.finished_at >= start,
        GameSession.finished_at < end, GameSession.awarded > 0)) or 0
    plants = db.scalar(select(func.count()).select_from(GameSession).where(
        GameSession.player_id == player.id, GameSession.finished_at >= start,
        GameSession.finished_at < end, GameSession.species_awarded.is_not(None))) or 0
    claims = set(db.scalars(select(WeeklyClaim.quest_code).where(
        WeeklyClaim.player_id == player.id, WeeklyClaim.week_start == start.date())))
    amounts = {'WEEK_TOUCH_500': int(touches), 'WEEK_FOUR_SESSIONS': int(sessions),
               'WEEK_TWO_FINDS': int(plants)}
    return {'starts_at': start.isoformat(), 'resets_at': end.isoformat(),
            'quests': [dict(code=code, **meta, progress=min(amounts[code], meta['target']),
                            completed=amounts[code] >= meta['target'], claimed=code in claims)
                       for code, meta in WEEKLY_TASKS.items()]}


def claim_weekly(db: Session, player: Player, code: str, now: datetime | None = None) -> dict:
    now = now or utc_now()
    locked = db.scalar(select(Player).where(Player.id == player.id).with_for_update())
    if locked is None or code not in WEEKLY_TASKS:
        raise ValueError('Неизвестное недельное задание')
    start, _ = utc_period(now, 'week')
    already = db.scalar(select(WeeklyClaim).where(
        WeeklyClaim.player_id == player.id, WeeklyClaim.week_start == start.date(),
        WeeklyClaim.quest_code == code))
    if already:
        return {'already_claimed': True, 'xp_granted': 0, 'xp': locked.xp,
                'weekly': weekly_snapshot(db, locked, now)}
    snapshot = weekly_snapshot(db, locked, now)
    task = next(item for item in snapshot['quests'] if item['code'] == code)
    if not task['completed']:
        raise ValueError('Недельное испытание еще не выполнено')
    locked.xp += task['xp']
    db.add(WeeklyClaim(player_id=player.id, week_start=start.date(),
                       quest_code=code, claimed_at=now))
    db.commit()
    return {'already_claimed': False, 'xp_granted': task['xp'], 'xp': locked.xp,
            'weekly': weekly_snapshot(db, locked, now)}
