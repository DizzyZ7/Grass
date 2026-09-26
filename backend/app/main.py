"""Single HTTP service: signed auth, game API, Telegram webhook, static React app."""
from __future__ import annotations
import hmac
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Annotated
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .game import ACHIEVEMENTS, active_session, apply_batch, finish_session, public_player, session_view, start_session, unlocked, level_for_xp, get_achievement
from .models import Player, AchievementUnlock
from .schemas import BatchIn, PrivacyIn, SelectWorldIn
from .progress import claim_daily, claim_weekly, daily_snapshot, leaderboard, select_grass, select_location, weekly_snapshot, world_snapshot
from .field import claim_field_mission, field_report
from .security import InvalidTelegramData, verify_init_data

log = logging.getLogger('touch_grass')
settings = get_settings()
logging.basicConfig(level=settings.log_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')


class LocalLimiter:
    """Cheap request DoS guard, only per process. Database locks enforce rewards globally."""
    def __init__(self) -> None:
        self.windows: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def allowed(self, key: str, limit: int, window: int = 60) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.windows[key]
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            # Bound key cardinality (attackers cannot force unbounded process memory).
            if len(self.windows) > 5000:
                self.windows = defaultdict(deque, {k: v for k, v in self.windows.items()
                                                    if v and now - v[-1] < window})
            return True


limiter = LocalLimiter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_production()
    app.state.bot = None
    app.state.dispatcher = None
    app.state.bot_username = ''
    if settings.bot_token:
        from aiogram import Bot, Dispatcher
        from aiogram.client.default import DefaultBotProperties
        from aiogram.types import MenuButtonWebApp, WebAppInfo
        from .bot import router
        bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode='HTML'))
        dp = Dispatcher()
        dp.include_router(router)
        # Inject dependency for /start via dispatcher workflow data.
        dp['public_url'] = settings.public_base_url.rstrip('/')
        try:
            me = await bot.get_me()
            app.state.bot_username = me.username or ''
            if settings.public_base_url:
                await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                    text='🌱 TOUCH GRASS.exe', web_app=WebAppInfo(url=settings.public_base_url.rstrip('/'))))
                await bot.set_webhook(f'{settings.public_base_url.rstrip("/")}/api/telegram/webhook',
                                      secret_token=settings.webhook_secret, allowed_updates=['message'])
            app.state.bot, app.state.dispatcher = bot, dp
        except Exception:
            await bot.session.close()
            raise
    yield
    if app.state.bot:
        await app.state.bot.session.close()


app = FastAPI(title='TOUCH GRASS.exe', version='0.4.0', lifespan=lifespan,
              docs_url='/api/docs' if settings.dev_mode else None,
              redoc_url=None, openapi_url='/api/openapi.json' if settings.dev_mode else None)


@app.middleware('http')
async def limit_by_ip(request: Request, call_next):
    # Do not trust X-Forwarded-For from the internet. For legitimate forwarded
    # addresses, configure your edge reverse proxy and trusted IPs explicitly.
    ip = request.client.host if request.client else 'unknown'
    if request.url.path.startswith('/api/') and not limiter.allowed(f'ip:{ip}', 3000):
        return JSONResponse(status_code=429, content={'detail': 'Слишком часто. Газону нужен перерыв.'})
    try:
        response = await call_next(request)
    except Exception:
        # Never log Authorization headers or initData.
        log.exception('Unhandled request error at %s', request.url.path)
        raise
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def player_auth(request: Request, db: Session = Depends(get_db)) -> Player:
    raw = request.headers.get('X-Telegram-Init-Data', '')
    if settings.dev_mode and not raw:
        # Intentionally insecure fake user, enabled EXCLUSIVELY by DEV_MODE.
        # Production startup must leave DEV_MODE=false.
        demo_id = request.headers.get('X-Demo-User', '')
        if not demo_id.isdecimal() or not 0 < int(demo_id) < 10**10:
            raise HTTPException(401, 'Open through Telegram, or set X-Demo-User in local DEV_MODE')
        identity = {'id': int(demo_id), 'first_name': 'DizZy [demo]', 'username': None, 'referrer_id': None}
    else:
        try:
            identity = verify_init_data(raw, settings.bot_token)
        except InvalidTelegramData as exc:
            raise HTTPException(401, str(exc)) from exc
    if not limiter.allowed(f'user:{identity["id"]}', 120):
        raise HTTPException(429, 'Слишком много запросов')
    player = db.get(Player, identity['id'])
    if player is None:
        referrer_id = identity.get('referrer_id')
        inviter = db.scalar(select(Player).where(Player.id == referrer_id).with_for_update()) if referrer_id else None
        player = Player(id=identity['id'], first_name=identity['first_name'],
                        username=identity['username'], recent_jokes=[],
                        referrer_id=inviter.id if inviter else None)
        if inviter and not db.scalar(select(AchievementUnlock).where(
                AchievementUnlock.player_id == inviter.id, AchievementUnlock.code == 'INVITE_FRIEND')):
            db.add(AchievementUnlock(player_id=inviter.id, code='INVITE_FRIEND'))
        db.add(player)
        try:
            db.commit()
        except IntegrityError:  # concurrent initial Mini App opens
            db.rollback()
            player = db.get(Player, identity['id'])
            if player is None:
                raise
    elif player.first_name != identity['first_name'] or player.username != identity['username']:
        player.first_name = identity['first_name']
        player.username = identity['username']
        db.commit()
    return player


PlayerAuth = Annotated[Player, Depends(player_auth)]
DB = Annotated[Session, Depends(get_db)]


@app.get('/healthz')
def health(db: DB):
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'game': 'TOUCH GRASS.exe'}


@app.get('/api/config')
def public_config(request: Request):
    return {'demo_mode': settings.dev_mode, 'bot_username': getattr(request.app.state, 'bot_username', ''),
            'share_url': (f'https://t.me/{request.app.state.bot_username}' if
                          getattr(request.app.state, 'bot_username', '') else settings.public_base_url)}


@app.get('/api/me')
def me(player: PlayerAuth, db: DB):
    snapshot = public_player(db, player)
    # Never ship undiscovered hidden achievement names in /api/me.
    visible = {code: meta for code, meta in ACHIEVEMENTS.items()
               if not meta.get('secret') or code in snapshot['achievements']}
    return {'player': snapshot,
            'active_session': session_view(active_session(db, player.id)),
            'achievement_catalog': visible}


@app.post('/api/sessions', status_code=201)
def session_start(player: PlayerAuth, db: DB):
    session, joke = start_session(db, player)
    return {'session': session_view(session), 'player': public_player(db, player), 'joke': joke}


@app.post('/api/sessions/{session_id}/batches')
def batch_apply(session_id: str, batch: BatchIn, player: PlayerAuth, db: DB):
    try:
        return apply_batch(db, player.id, session_id, batch)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@app.post('/api/sessions/{session_id}/finish')
def session_finish(session_id: str, player: PlayerAuth, db: DB):
    try:
        return finish_session(db, player.id, session_id)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc


@app.get('/api/world')
def world(player: PlayerAuth, db: DB):
    return world_snapshot(db, player, level_for_xp(player.xp), set(unlocked(db, player.id)))


@app.post('/api/world/location')
def world_location(change: SelectWorldIn, player: PlayerAuth, db: DB):
    try:
        code = select_location(db, player, change.code, level_for_xp(player.xp),
                               set(unlocked(db, player.id)))
        if code != 'windowsill':
            get_achievement(db, player.id, 'TRAVELER', [])
            db.commit()
        return {'selected_location': code, 'player': public_player(db, player)}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(403, str(exc)) from exc


@app.post('/api/world/grass')
def world_grass(change: SelectWorldIn, player: PlayerAuth, db: DB):
    try:
        code = select_grass(db, player, change.code)
        return {'selected_grass': code, 'player': public_player(db, player)}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(403, str(exc)) from exc


@app.get('/api/daily')
def daily(player: PlayerAuth, db: DB):
    return daily_snapshot(db, player)


@app.post('/api/daily/claim/{code}')
def daily_claim(code: str, player: PlayerAuth, db: DB):
    try:
        reward = claim_daily(db, player, code)
        return {**reward, 'player': public_player(db, player)}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@app.get('/api/field-report')
def get_field_report(player: PlayerAuth, db: DB):
    return field_report(db, player)


@app.post('/api/field-report/claim')
def claim_field(player: PlayerAuth, db: DB):
    try:
        result = claim_field_mission(db, player)
        return {**result, 'player': public_player(db, player)}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@app.get('/api/weekly')
def weekly(player: PlayerAuth, db: DB):
    return weekly_snapshot(db, player)


@app.post('/api/weekly/claim/{code}')
def weekly_claim(code: str, player: PlayerAuth, db: DB):
    try:
        reward = claim_weekly(db, player, code)
        return {**reward, 'player': public_player(db, player)}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc


@app.post('/api/profile/privacy')
def update_privacy(change: PrivacyIn, player: PlayerAuth, db: DB):
    locked = db.get(Player, player.id, with_for_update=True)
    locked.show_public_profile = change.show_public_profile
    db.commit()
    return {'player': public_player(db, locked)}


@app.get('/api/leaderboard')
def top_players(player: PlayerAuth, db: DB, period: str = 'day'):
    if period not in ('day', 'week'):
        raise HTTPException(422, 'Only day/week periods are supported')
    return leaderboard(db, period)


@app.get('/api/players/{player_id}')
def public_profile(player_id: int, player: PlayerAuth, db: DB):
    target = db.get(Player, player_id)
    if not target or (not target.show_public_profile and target.id != player.id):
        raise HTTPException(404, 'Player not found')
    data = public_player(db, target)
    public = {key: data[key] for key in ('id', 'first_name', 'username', 'total_touches',
             'level', 'sessions_completed', 'achievements', 'best_streak', 'invite_count')}
    public['achievement_catalog'] = {code: ACHIEVEMENTS[code] for code in data['achievements']
                                     if code in ACHIEVEMENTS}
    return public


@app.post('/api/telegram/webhook', include_in_schema=False)
async def telegram_webhook(request: Request,
                           x_telegram_bot_api_secret_token: str = Header(default='')):
    if not settings.bot_token or not request.app.state.bot:
        raise HTTPException(503, 'Telegram bot is not configured')
    if not hmac.compare_digest(x_telegram_bot_api_secret_token, settings.webhook_secret):
        raise HTTPException(403, 'Invalid webhook secret')
    from aiogram.types import Update
    update = Update.model_validate(await request.json(), context={'bot': request.app.state.bot})
    await request.app.state.dispatcher.feed_update(request.app.state.bot, update)
    return {'ok': True}


DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if (DIST / 'assets').exists():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')


@app.get('/favicon.svg', include_in_schema=False)
def favicon():
    file = DIST / 'favicon.svg'
    if not file.exists():
        raise HTTPException(404, 'Not found')
    return FileResponse(file, media_type='image/svg+xml')


@app.get('/{page:path}', include_in_schema=False)
def spa(page: str):
    if page.startswith(('api/', 'assets/')) or '.' in page or not (DIST / 'index.html').exists():
        raise HTTPException(404, 'Not found')
    return FileResponse(DIST / 'index.html', headers={'Cache-Control': 'no-cache'})
