"""Stage-3 social regression tests: privacy, signed-only invites and weekly payouts."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import new
import json
import time
from urllib.parse import urlencode

import pytest
from sqlalchemy import select

from backend.app.game import ACHIEVEMENTS
from backend.app.main import settings
from backend.app.models import BatchReceipt, GameSession, Player, WeeklyClaim
from backend.app.progress import claim_weekly, leaderboard, weekly_snapshot
from backend.app.security import InvalidTelegramData, verify_init_data

TOKEN = '123456:real-looking-fixture'
AUTH = {'X-Demo-User': '1337001'}


def signed(user_id=1337002, param='ref_1337001'):
    values = {'auth_date': str(int(time.time())),
              'user': json.dumps({'id': user_id, 'first_name': 'Мемный новичок'}),
              'start_param': param}
    text = '\n'.join(f'{key}={value}' for key, value in sorted(values.items()))
    secret = new(b'WebAppData', TOKEN.encode(), sha256).digest()
    values['hash'] = new(secret, text.encode(), sha256).hexdigest()
    return urlencode(values)


def test_referrer_only_accepted_when_signed():
    raw = signed()
    assert verify_init_data(raw, TOKEN)['referrer_id'] == 1337001
    assert verify_init_data(signed(param='ref_1337002'), TOKEN)['referrer_id'] is None
    assert verify_init_data(signed(param='ref_-1'), TOKEN)['referrer_id'] is None
    assert verify_init_data(signed(param='ref_999999999999999999999'), TOKEN)['referrer_id'] is None
    with pytest.raises(InvalidTelegramData):
        verify_init_data(raw.replace('ref_1337001', 'ref_1337004'), TOKEN)


def test_signup_invite_once_no_invite_xp(client, session_factory, monkeypatch):
    monkeypatch.setattr(settings, 'bot_token', TOKEN)
    inviter = client.get('/api/me', headers=AUTH).json()['player']
    assert inviter['invite_count'] == 0
    new_headers = {'X-Telegram-Init-Data': signed()}
    first = client.get('/api/me', headers=new_headers)
    assert first.status_code == 200
    assert first.json()['player']['xp'] == 0
    result = client.get('/api/me', headers=AUTH).json()['player']
    assert result['invite_count'] == 1
    assert 'INVITE_FRIEND' in result['achievements']
    client.get('/api/me', headers=new_headers)
    assert client.get('/api/me', headers=AUTH).json()['player']['invite_count'] == 1
    with session_factory() as db:
        assert db.get(Player, 1337002).referrer_id == 1337001
        assert db.get(Player, 1337001).xp == 0


def test_hide_profile_removes_from_ranking_and_lookup(client, session_factory):
    client.get('/api/me', headers=AUTH)
    with session_factory() as db:
        db.add(BatchReceipt(player_id=1337001, session_id='test-session', batch_id='x',
                            seq=1, requested=40, awarded=40, created_at=datetime.now(timezone.utc)))
        # Real FK requires matching session.
        db.add(GameSession(id='test-session', player_id=1337001, awarded=40,
                           started_at=datetime.now(timezone.utc), last_award_at=datetime.now(timezone.utc)))
        db.commit()
    other = {'X-Demo-User': '1337003'}
    client.get('/api/me', headers=other)
    assert len(client.get('/api/leaderboard', headers=other).json()['leaders']) == 1
    hidden = client.post('/api/profile/privacy', json={'show_public_profile': False}, headers=AUTH)
    assert hidden.status_code == 200 and hidden.json()['player']['show_public_profile'] is False
    assert client.get('/api/leaderboard', headers=other).json()['leaders'] == []
    assert client.get('/api/players/1337001', headers=other).status_code == 404
    assert client.get('/api/players/1337001', headers=AUTH).status_code == 200
    assert client.post('/api/profile/privacy', json={'show_public_profile': []}, headers=AUTH).status_code == 422
    assert client.post('/api/profile/privacy', json={'show_public_profile': True}, headers=AUTH).status_code == 200
    assert len(client.get('/api/leaderboard', headers=other).json()['leaders']) == 1


def test_weekly_rewards_boundary_replays_and_no_client_scores(session_factory):
    now = datetime(2026, 9, 23, 14, 0, tzinfo=timezone.utc)  # Wednesday UTC
    with session_factory() as db:
        player = Player(id=803, first_name='Senior Lawn', recent_jokes=[])
        db.add(player)
        db.flush()
        session = GameSession(id='weekly-test', player_id=803, started_at=now,
                              last_award_at=now, finished_at=now + timedelta(seconds=30), awarded=500,
                              species_awarded='meadow')
        db.add(session)
        db.add(BatchReceipt(player_id=803, session_id='weekly-test', batch_id='weekly-batch',
                            seq=1, requested=80, awarded=500, created_at=now))
        db.commit()
        snapshot = weekly_snapshot(db, player, now + timedelta(minutes=1))
        assert snapshot['starts_at'] == '2026-09-21T00:00:00+00:00'
        assert snapshot['quests'][0]['completed']
        assert not snapshot['quests'][1]['completed']
        assert snapshot['quests'][2]['progress'] == 1
        with pytest.raises(ValueError):
            claim_weekly(db, player, 'WEEK_FOUR_SESSIONS', now)
        db.rollback()
        first = claim_weekly(db, player, 'WEEK_TOUCH_500', now)
        replay = claim_weekly(db, player, 'WEEK_TOUCH_500', now)
        assert first['xp_granted'] == 180
        assert replay['xp_granted'] == 0 and replay['already_claimed']
        assert db.get(Player, 803).xp == 180
        assert len(db.scalars(select(WeeklyClaim)).all()) == 1
        next_week = weekly_snapshot(db, player, now + timedelta(days=7))
        assert next_week['quests'][0]['progress'] == 0
        assert next_week['quests'][0]['claimed'] is False
        assert leaderboard(db, 'week', now + timedelta(days=7))['leaders'] == []


def test_hidden_achievement_metadata_and_impossible_rewards():
    secret = [item for item in ACHIEVEMENTS.values() if item.get('secret')]
    assert len(secret) >= 4
    assert 'INVITE_FRIEND' in ACHIEVEMENTS


def test_weekly_api_claim_and_hidden_catalog(client, session_factory):
    client.get('/api/me', headers=AUTH)
    catalog = client.get('/api/me', headers=AUTH).json()['achievement_catalog']
    assert 'ERROR_404' not in catalog and 'NIGHT_GARDENER' not in catalog
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        player = db.get(Player, 1337001)
        player.total_touches = 500
        db.add(GameSession(id='weekly-api-test', player_id=1337001, started_at=now,
                           last_award_at=now, finished_at=now, awarded=500))
        db.add(BatchReceipt(player_id=1337001, session_id='weekly-api-test',
                            batch_id='weekly-api-batch', seq=1, requested=80,
                            awarded=500, created_at=now))
        db.commit()
    weekly = client.get('/api/weekly', headers=AUTH)
    assert weekly.status_code == 200
    assert weekly.json()['quests'][0]['completed']
    claim = client.post('/api/weekly/claim/WEEK_TOUCH_500', headers=AUTH)
    assert claim.status_code == 200 and claim.json()['xp_granted'] == 180
    replay = client.post('/api/weekly/claim/WEEK_TOUCH_500', headers=AUTH)
    assert replay.status_code == 200 and replay.json()['xp_granted'] == 0
    assert replay.json()['player']['xp'] == 180
    assert client.post('/api/weekly/claim/WEEK_FOUR_SESSIONS', headers=AUTH).status_code == 409
    assert client.post('/api/weekly/claim/NOT_A_QUEST', headers=AUTH).status_code == 409
    # Static API validation must reject coercible values rather than silently toggle privacy.
    assert client.post('/api/profile/privacy', json={'show_public_profile': 1}, headers=AUTH).status_code == 422
