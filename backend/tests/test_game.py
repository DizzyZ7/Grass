from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from backend.app.game import (ACHIEVEMENTS, apply_batch, finish_session,
                              level_for_xp, start_session, unlocked, xp_for_level)
from backend.app.jokes import JOKES, pick_joke
from backend.app.models import BatchReceipt, Player
from backend.app.schemas import BatchIn

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def make_player(session_factory):
    db = session_factory()
    db.add(Player(id=42, first_name='DizZy', recent_jokes=[]))
    db.commit()
    return db, db.get(Player, 42)


def batch(seq=1, touches=5, combo=4, batch_id=None):
    return BatchIn(batch_id=batch_id or uuid4(), seq=seq, touches=touches,
                   duration_ms=1700, peak_combo=combo)


def test_120_original_jokes_rotate_without_recent_repetition():
    assert len(JOKES) >= 100
    assert len({line for _, line in JOKES.values()}) == len(JOKES)
    recent = []
    ids = []
    for i in range(10):
        joke_id, _, recent = pick_joke('start', recent, str(i))
        ids.append(joke_id)
    assert len(ids) == len(set(ids))


def test_levels():
    assert [level_for_xp(x) for x in [0, 99, 100, 299, 300, 599, 600]] == [1, 1, 2, 2, 3, 3, 4]
    assert [xp_for_level(n) for n in range(1, 5)] == [0, 100, 300, 600]
    assert len(ACHIEVEMENTS) >= 5


def test_start_idempotent_active(session_factory):
    db, player = make_player(session_factory)
    first, first_joke = start_session(db, player, NOW)
    second, second_joke = start_session(db, player, NOW + timedelta(seconds=1))
    assert first.id == second.id and first_joke and second_joke == ''
    db.close()


def test_batch_once_even_after_network_retry(session_factory):
    db, player = make_player(session_factory)
    sess, _ = start_session(db, player, NOW)
    payload = batch()
    first = apply_batch(db, player.id, sess.id, payload, NOW + timedelta(seconds=1))
    retried = apply_batch(db, player.id, sess.id, payload, NOW + timedelta(seconds=2))
    assert first['granted'] == 5 and retried['granted'] == 5 and retried['duplicate']
    assert db.get(Player, 42).total_touches == 5
    assert db.scalar(select(func.count()).select_from(BatchReceipt)) == 1
    assert 'FIRST_TOUCH' in unlocked(db, 42)
    db.close()


def test_anti_cheat_caps_burst_and_persists_receipt(session_factory):
    db, player = make_player(session_factory)
    sess, _ = start_session(db, player, NOW)
    granted = apply_batch(db, player.id, sess.id, batch(touches=80, combo=80), NOW + timedelta(milliseconds=30))
    assert granted['granted'] <= 5
    assert granted['requested'] == 80
    assert db.get(Player, 42).total_touches <= 5
    assert sess.flags == 1
    db.close()


def test_reject_non_monotonic_sequences(session_factory):
    db, player = make_player(session_factory)
    sess, _ = start_session(db, player, NOW)
    with pytest.raises(ValueError, match='Out-of-order'):
        apply_batch(db, 42, sess.id, batch(seq=3), NOW + timedelta(seconds=2))
    db.rollback()
    assert db.get(Player, 42).total_touches == 0
    db.close()


def test_cross_player_receipt_rejected(session_factory):
    db, player = make_player(session_factory)
    sess, _ = start_session(db, player, NOW)
    db.add(Player(id=24, first_name='Other', recent_jokes=[])); db.commit()
    with pytest.raises(LookupError):
        apply_batch(db, 24, sess.id, batch(), NOW + timedelta(seconds=2))
    db.close()


def test_finish_exactly_once(session_factory):
    db, player = make_player(session_factory)
    sess, _ = start_session(db, player, NOW)
    apply_batch(db, 42, sess.id, batch(), NOW + timedelta(seconds=1))
    finish_session(db, 42, sess.id, NOW + timedelta(seconds=2))
    finish_session(db, 42, sess.id, NOW + timedelta(seconds=3))
    assert db.get(Player, 42).sessions_completed == 1
    assert 'FIRST_SESSION' in unlocked(db, 42)
    with pytest.raises(ValueError, match='finished'):
        apply_batch(db, 42, sess.id, batch(seq=2), NOW + timedelta(seconds=4))
    db.close()


def test_sessions_expire(session_factory):
    db, player = make_player(session_factory)
    sess, _ = start_session(db, player, NOW)
    with pytest.raises(ValueError, match='expired'):
        apply_batch(db, 42, sess.id, batch(), NOW + timedelta(minutes=6))
    db.close()
