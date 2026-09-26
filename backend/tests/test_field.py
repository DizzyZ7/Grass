"""Server-authoritative rotating expedition and deterministic weather regressions."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.app.field import MISSIONS, claim_field_mission, field_report
from backend.app.models import BatchReceipt, FieldMission, GameSession, Player
from backend.app.weather import FORECASTS, weather_for
from backend.app.world import LOCATIONS

HEADERS = {'X-Demo-User': '777001'}


def test_weather_is_deterministic_and_location_specific():
    day = datetime(2026, 9, 26, tzinfo=timezone.utc).date()
    forecasts = [weather_for(place, day) for place in LOCATIONS]
    assert all(item['code'] in FORECASTS for item in forecasts)
    assert all(item['date'] == '2026-09-26' for item in forecasts)
    assert [weather_for(place, day) for place in LOCATIONS] == forecasts
    assert len({item['code'] for item in forecasts}) >= 2


def test_personal_mission_frozen_and_unchanged_after_location_switch(client, session_factory):
    assert client.get('/api/me', headers=HEADERS).status_code == 200
    with session_factory() as db:
        db.get(Player, 777001).xp = 1200
        db.commit()
    first = client.get('/api/field-report', headers=HEADERS)
    assert first.status_code == 200
    a = first.json()
    assert a['mission']['code'] in MISSIONS
    assert a['weather']['location'] == 'windowsill'
    assert a['mission']['claimed'] is False
    assert client.post('/api/world/location', headers=HEADERS, json={'code': 'neighborhood'}).status_code == 200
    second = client.get('/api/field-report', headers=HEADERS)
    assert second.status_code == 200
    b = second.json()
    assert b['mission'] == a['mission']
    assert b['weather']['location'] == 'neighborhood'
    with session_factory() as db:
        assert len(db.scalars(select(FieldMission).where(FieldMission.player_id == 777001)).all()) == 1


def _qualifying_sessions(db, code: str, location: str | None, player_id: int, now: datetime):
    requested = 2 if code == 'two_outings' else 1
    for number in range(requested):
        earned = {'touch_90': 90, 'two_outings': 25, 'strong_session': 70,
                  'home_visit': 45, 'foreign_visit': 40}[code]
        session = GameSession(player_id=player_id, started_at=now,
                              last_award_at=now, finished_at=now, location_code=location or 'windowsill',
                              awarded=earned, last_seq=1)
        db.add(session)
        db.flush()
        if code == 'touch_90':
            db.add(BatchReceipt(player_id=player_id, session_id=session.id,
                                batch_id=str(uuid4()), seq=1, requested=earned, awarded=earned,
                                created_at=now, joke_id=None, new_achievements=[]))


@pytest.mark.parametrize('code', list(MISSIONS))
def test_claim_each_mission_once_and_never_accept_client_scores(code, client, session_factory):
    client.get('/api/me', headers=HEADERS)
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add(FieldMission(player_id=777001, day=now.date(), code=code,
                            location_code='windowsill' if code in {'home_visit', 'foreign_visit'} else None,
                            xp=MISSIONS[code]['xp'], created_at=now))
        db.commit()
    assert client.post('/api/field-report/claim', headers=HEADERS, json={'touches': 100000}).status_code == 409
    with session_factory() as db:
        _qualifying_sessions(db, code, 'windowsill', 777001, now)
        db.commit()
    earned = client.post('/api/field-report/claim', headers=HEADERS)
    assert earned.status_code == 200, earned.text
    assert earned.json()['xp_granted'] == MISSIONS[code]['xp']
    assert earned.json()['report']['mission']['claimed'] is True
    assert earned.json()['new_achievements'] == []
    second = client.post('/api/field-report/claim', headers=HEADERS)
    assert second.status_code == 200
    assert second.json()['already_claimed'] is True
    assert second.json()['xp_granted'] == 0
    assert second.json()['player']['xp'] == earned.json()['player']['xp']


def test_mission_isolation_and_protected_location(client, session_factory):
    client.get('/api/me', headers=HEADERS)
    with session_factory() as db:
        player = db.get(Player, 777001)
        now = datetime.now(timezone.utc)
        mission = FieldMission(player_id=player.id, day=now.date(), code='foreign_visit',
                               location_code='neighborhood', xp=115, created_at=now)
        db.add(mission)
        _qualifying_sessions(db, 'foreign_visit', 'windowsill', player.id, now)
        db.commit()
    assert client.post('/api/field-report/claim', headers=HEADERS).status_code == 409
    with session_factory() as db:
        _qualifying_sessions(db, 'foreign_visit', 'neighborhood', 777001, datetime.now(timezone.utc))
        db.commit()
    assert client.post('/api/field-report/claim', headers=HEADERS).status_code == 200


def test_field_badges_after_three_days(session_factory):
    with session_factory() as db:
        now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        player = Player(id=777001, first_name='Grass researcher', xp=1000)
        db.add(player)
        db.flush()
        for offset in (2, 1):
            day = now - timedelta(days=offset)
            db.add(FieldMission(player_id=player.id, day=day.date(), code='touch_90',
                                xp=80, created_at=day, claimed_at=day))
        db.add(FieldMission(player_id=player.id, day=now.date(), code='touch_90', xp=80,
                            created_at=now))
        _qualifying_sessions(db, 'touch_90', None, player.id, now)
        db.commit()
        result = claim_field_mission(db, player, now)
        assert result['new_achievements'] == ['FIELD_SCOUT']
        assert result['report']['missions_completed'] == 3


def test_two_players_get_independent_daily_assignments(session_factory):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    with session_factory() as db:
        a = Player(id=31, first_name='A')
        b = Player(id=32, first_name='B')
        db.add_all([a, b])
        db.commit()
        x, y = field_report(db, a, now), field_report(db, b, now)
        assert x['date'] == y['date']
        assert db.scalar(select(FieldMission).where(FieldMission.player_id == 31)).player_id == 31
        assert db.scalar(select(FieldMission).where(FieldMission.player_id == 32)).player_id == 32


def test_rainy_session_unlocks_secret_only_with_server_stored_data(session_factory):
    from backend.app.game import finish_session
    from backend.app.weather import weather_for
    from datetime import date
    with session_factory() as db:
        player = Player(id=100005, first_name='Storm', xp=500)
        db.add(player)
        db.flush()
        day = date(2026, 9, 26)
        while weather_for('windowsill', day)['code'] != 'rainy':
            day += timedelta(days=1)
        started = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
        session = GameSession(player_id=player.id, started_at=started, last_award_at=started,
                              location_code='windowsill', awarded=40, last_seq=1)
        db.add(session)
        db.commit()
        first = finish_session(db, player.id, session.id, started + timedelta(seconds=60))
        assert 'STORM_WALKER' in first['new_achievements']
        second = finish_session(db, player.id, session.id, started + timedelta(seconds=61))
        assert second['new_achievements'] == []
