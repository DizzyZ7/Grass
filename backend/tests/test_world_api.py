from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from backend.app.models import Player

AUTH = {'X-Demo-User': '990001'}


def test_stage2_api_auth_and_catalog(client):
    for endpoint in ('/api/world', '/api/daily', '/api/leaderboard', '/api/players/990001'):
        assert client.get(endpoint).status_code == 401
    payload = client.get('/api/world', headers=AUTH).json()
    assert len(payload['locations']) == 7
    assert len(payload['species']) == 14
    assert payload['selected_location'] == 'windowsill'
    assert client.get('/api/leaderboard?period=month', headers=AUTH).status_code == 422
    assert client.post('/api/daily/claim/TOUCH_80', headers=AUTH).status_code == 409
    assert client.post('/api/world/location', json={'code': 'forbidden'}, headers=AUTH).status_code == 403
    assert client.post('/api/world/grass', json={'code': 'cosmic_admin'}, headers=AUTH).status_code == 403
    assert client.post('/api/world/grass', json={'code': 'meadow'}, headers=AUTH).status_code == 200
    assert client.get('/api/players/990001', headers=AUTH).json()['first_name'] == 'DizZy [demo]'


def test_stage2_api_travel_and_daily_claim(client, session_factory):
    client.get('/api/me', headers=AUTH)
    with session_factory() as db:
        player = db.get(Player, 990001)
        player.xp = 100
        db.commit()
    response = client.post('/api/world/location', json={'code':'neighborhood'}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()['player']['selected_location'] == 'neighborhood'
    assert 'TRAVELER' in response.json()['player']['achievements']
    daily = client.get('/api/daily', headers=AUTH).json()
    assert daily['streak'] == 0 and len(daily['quests']) == 3


def test_http_end_to_end_find_claim_equip_and_replay(client, monkeypatch):
    """A full gameplay cycle must survive API serialization and idempotent retries."""
    from uuid import uuid4
    import backend.app.game as game
    import backend.app.progress as progress
    clock = [datetime(2026, 9, 26, 11, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(game, 'utc_now', lambda: clock[0])
    monkeypatch.setattr(progress, 'utc_now', lambda: clock[0])
    profile = client.get('/api/me', headers=AUTH).json()['player']
    assert profile['total_touches'] == 0
    created = client.post('/api/sessions', headers=AUTH)
    assert created.status_code == 201
    session_id = created.json()['session']['id']
    clock[0] += timedelta(seconds=6)
    payload = {'batch_id': str(uuid4()), 'seq': 1, 'touches': 80, 'duration_ms': 4000, 'peak_combo': 14}
    path = f'/api/sessions/{session_id}/batches'
    receipt = client.post(path, json=payload, headers=AUTH)
    assert receipt.status_code == 200 and receipt.json()['granted'] == 80
    replay = client.post(path, json=payload, headers=AUTH)
    assert replay.status_code == 200 and replay.json()['duplicate']
    clock[0] += timedelta(seconds=2)
    result = client.post(f'/api/sessions/{session_id}/finish', headers=AUTH)
    assert result.status_code == 200
    plant = result.json()['new_plant']
    assert plant and plant['code']
    duplicate_finish = client.post(f'/api/sessions/{session_id}/finish', headers=AUTH)
    assert duplicate_finish.json()['new_plant'] is None
    assert duplicate_finish.json()['player']['sessions_completed'] == 1
    day = client.get('/api/daily', headers=AUTH).json()
    assert {q['code'] for q in day['quests'] if q['completed']} == {'TOUCH_80', 'FIND_GRASS'}
    claim = client.post('/api/daily/claim/TOUCH_80', headers=AUTH)
    assert claim.status_code == 200 and claim.json()['xp_granted'] == 35
    assert client.post('/api/daily/claim/TOUCH_80', headers=AUTH).json()['xp_granted'] == 0
    equip = client.post('/api/world/grass', json={'code': plant['code']}, headers=AUTH)
    assert equip.status_code == 200
    assert equip.json()['player']['selected_grass'] == plant['code']
    rank = client.get('/api/leaderboard?period=day', headers=AUTH).json()['leaders']
    assert rank[0]['touches'] == 80
