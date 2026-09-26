from uuid import uuid4


def auth():
    return {'X-Demo-User': '777001'}


def test_health_and_spa(client):
    assert client.get('/healthz').json()['status'] == 'ok'
    assert client.get('/api/missing').status_code == 404


def test_protect_game_without_init_data(client):
    assert client.get('/api/me').status_code == 401
    assert client.post('/api/sessions').status_code == 401


def test_api_progress_and_double_finish(client):
    me = client.get('/api/me', headers=auth())
    assert me.status_code == 200 and me.json()['player']['total_touches'] == 0
    start = client.post('/api/sessions', headers=auth())
    assert start.status_code == 201
    sid = start.json()['session']['id']
    payload = {'batch_id': str(uuid4()), 'seq': 1, 'touches': 2, 'duration_ms': 100, 'peak_combo': 1}
    response = client.post(f'/api/sessions/{sid}/batches', json=payload, headers=auth())
    assert response.status_code == 200, response.text
    duplicate = client.post(f'/api/sessions/{sid}/batches', json=payload, headers=auth())
    assert duplicate.status_code == 200 and duplicate.json()['duplicate'] is True
    finished = client.post(f'/api/sessions/{sid}/finish', headers=auth())
    assert finished.status_code == 200
    again = client.post(f'/api/sessions/{sid}/finish', headers=auth())
    assert again.status_code == 200
    assert again.json()['player']['sessions_completed'] == 1


def test_invalid_payload_and_cross_player(client):
    sid = client.post('/api/sessions', headers=auth()).json()['session']['id']
    payload = {'batch_id': str(uuid4()), 'seq': 1, 'touches': 8000,
               'duration_ms': 100, 'peak_combo': 1}
    assert client.post(f'/api/sessions/{sid}/batches', json=payload, headers=auth()).status_code == 422
    assert client.post(f'/api/sessions/{sid}/finish', headers={'X-Demo-User': '777002'}).status_code == 404


def test_webhook_requires_bot(client):
    assert client.post('/api/telegram/webhook', json={'update_id': 1}).status_code == 503
