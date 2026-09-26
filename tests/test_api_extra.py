"""HTTP contract, auth guards, and persistence without real Telegram services."""
import os
os.environ['DEV_MODE'] = 'true'
os.environ['BOT_TOKEN'] = ''
os.environ['DATABASE_URL'] = 'sqlite://'
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.db import Base, get_db
from backend.app.main import app


def test_end_to_end():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    def db_override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = db_override
    try:
        with TestClient(app) as client:
            assert client.get('/healthz').json()['status'] == 'ok'
            assert client.get('/api/me').status_code == 401
            headers = {'X-Demo-User': '987654'}
            me = client.get('/api/me', headers=headers)
            assert me.status_code == 200
            assert me.json()['player']['total_touches'] == 0
            sess = client.post('/api/sessions', headers=headers).json()['session']['id']
            payload = {'batch_id': '93658932-e9d5-445c-bf57-bdbfa045bf73',
                       'seq': 1, 'touches': 8, 'duration_ms': 2000, 'peak_combo': 0}
            r = client.post(f'/api/sessions/{sess}/batches', headers=headers, json=payload)
            assert r.status_code == 200
            assert 0 <= r.json()['granted'] <= 8
            assert client.post(f'/api/sessions/{sess}/batches', headers=headers,
                               json=payload).json()['duplicate']
            assert client.post(f'/api/sessions/{sess}/batches', headers=headers,
                               json={**payload, 'batch_id': 'new'}).status_code == 422
            result = client.post(f'/api/sessions/{sess}/finish', headers=headers)
            assert result.status_code == 200
            assert result.json()['session']['finished']
            assert client.get('/api/me', headers=headers).json()['active_session'] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
