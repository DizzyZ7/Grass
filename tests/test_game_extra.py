"""Real ORM transactions through a disposable SQLite DB; production uses PostgreSQL locks."""
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.db import Base
from backend.app.models import Player, AchievementUnlock, BatchReceipt, utc_now
from backend.app.game import (ACHIEVEMENTS, active_session, apply_batch, finish_session,
                              level_for_xp, start_session, xp_for_level)
from backend.app.jokes import LINES, JOKES, pick_joke
from backend.app.schemas import BatchIn


@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as db:
        yield db
    engine.dispose()


def batch(seq=1, touches=20, combo=0, batch_id=None):
    return BatchIn(batch_id=batch_id or uuid4(), seq=seq, touches=touches, duration_ms=1500,
                   peak_combo=combo)


def player(db):
    p = Player(id=42, first_name='DizZy', username='dizzyz7', recent_jokes=[])
    db.add(p)
    db.commit()
    return p


def test_first_touch_exactly_once_and_achievements(db):
    p = player(db)
    now = utc_now()
    sess, joke = start_session(db, p, now=now)
    assert joke
    b = batch(touches=16)
    result = apply_batch(db, p.id, sess.id, b, now=now + timedelta(seconds=2))
    assert result['granted'] == 16
    assert result['new_achievements'] == ['FIRST_TOUCH']
    assert level_for_xp(result['xp']) == 1
    again = apply_batch(db, p.id, sess.id, b, now=now + timedelta(seconds=4))
    assert again['duplicate'] is True
    assert again['granted'] == 16
    assert db.get(Player, 42).total_touches == 16
    assert db.scalar(select(BatchReceipt)).seq == 1
    assert db.scalar(select(AchievementUnlock)).code == 'FIRST_TOUCH'
    with pytest.raises(ValueError):
        apply_batch(db, p.id, sess.id, batch(seq=3), now=now + timedelta(seconds=5))
    db.rollback()


def test_server_clamps_impossible_rate(db):
    p = player(db)
    now = utc_now()
    sess, _ = start_session(db, p, now=now)
    first = apply_batch(db, p.id, sess.id, batch(touches=80), now=now)
    assert first['granted'] == 4
    assert db.get(Player, 42).xp == 4
    second = apply_batch(db, p.id, sess.id, batch(seq=2, touches=80), now=now + timedelta(seconds=1))
    assert second['granted'] <= 22
    assert db.get(Player, 42).total_touches <= 26


def test_start_resume_expiration_finish_idempotent(db):
    p = player(db)
    now = utc_now()
    sess, _ = start_session(db, p, now=now)
    same, _ = start_session(db, p, now=now + timedelta(seconds=5))
    assert sess.id == same.id
    apply_batch(db, p.id, sess.id, batch(touches=3), now=now + timedelta(seconds=1))
    ended = finish_session(db, p.id, sess.id, now=now + timedelta(seconds=3))
    assert ended['session']['finished']
    assert ended['new_achievements'] == ['FIRST_SESSION']
    finish_session(db, p.id, sess.id, now=now + timedelta(seconds=4))
    assert db.get(Player, 42).sessions_completed == 1
    with pytest.raises(ValueError):
        apply_batch(db, p.id, sess.id, batch(seq=2), now=now + timedelta(seconds=5))
    db.rollback()
    new, _ = start_session(db, p, now=now + timedelta(seconds=5))
    assert new.id != sess.id
    assert active_session(db, p.id, now + timedelta(minutes=6)) is None


def test_jokes_and_level_formula():
    assert len(JOKES) >= 100
    assert all(len(lines) >= 20 for lines in LINES.values())
    for kind in LINES:
        first, _, recent = pick_joke(kind, [], 'test')
        second, _, _ = pick_joke(kind, recent, 'test')
        assert first != second
    assert level_for_xp(0) == 1
    assert level_for_xp(100) == 2
    assert level_for_xp(300) == 3
    assert xp_for_level(3) == 300
    assert len(ACHIEVEMENTS) >= 5
