import os
os.environ['DEV_MODE'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'
os.environ.pop('BOT_TOKEN', None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from backend.app.db import Base, get_db
from backend.app.main import app, limiter
from backend.app import models  # noqa: F401


@pytest.fixture
def session_factory():
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    def factory() -> Session:
        return Session(engine, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def client(session_factory):
    def dependency():
        with session_factory() as db:
            yield db
    limiter.windows.clear()
    app.dependency_overrides[get_db] = dependency
    with TestClient(app) as api:
        yield api
    app.dependency_overrides.clear()
