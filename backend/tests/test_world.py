"""Stage-2 economy regression tests: server-owned progress, daily UTC and replay."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.game import apply_batch, finish_session, level_for_xp, start_session
from backend.app.models import BatchReceipt, DailyClaim, GameSession, GrassUnlock, Player
from backend.app.progress import (claim_daily, collection, daily_snapshot, leaderboard,
                                  record_activity, select_grass, select_location, world_snapshot)
from backend.app.schemas import BatchIn
from backend.app.world import LOCATIONS, RARITIES, SPECIES, can_visit, discover_species

NOW = datetime(2026, 9, 26, 10, 30, tzinfo=timezone.utc)


def make_player(session_factory, player_id=101):
    db = session_factory()
    player = Player(id=player_id, first_name='DizZy', recent_jokes=[])
    db.add(player)
    db.commit()
    return db, player


def play(db, player, now=NOW, amount=60):
    game_session, _ = start_session(db, player, now)
    # 60 touches after four seconds fit within rate + burst; no client-set XP.
    payload = BatchIn(batch_id=uuid4(), seq=1, touches=min(80, amount), duration_ms=3500, peak_combo=14)
    receipt = apply_batch(db, player.id, game_session.id, payload, now + timedelta(seconds=5))
    if amount > 80:
        extra = BatchIn(batch_id=uuid4(), seq=2, touches=amount - 80, duration_ms=1800, peak_combo=14)
        apply_batch(db, player.id, game_session.id, extra, now + timedelta(seconds=7))
    finished = finish_session(db, player.id, game_session.id, now + timedelta(seconds=8))
    return receipt, finished


def test_world_has_nine_original_locations_and_five_rarities():
    assert len(LOCATIONS) == 9
    assert len(SPECIES) == 14
    assert len(RARITIES) == 5
    assert len({place.name for place in LOCATIONS.values()}) == 9
    assert len({item.name for item in SPECIES.values()}) == 14
    assert can_visit(5, set(), LOCATIONS['garden_404']) is False
    assert can_visit(5, {'GRASS_1000'}, LOCATIONS['garden_404']) is True
    assert can_visit(8, set(), LOCATIONS['friday_deploy']) is False
    assert can_visit(8, {'FRIDAY_DEPLOY'}, LOCATIONS['friday_deploy']) is True


def test_species_roll_is_deterministic_and_all_rarities_reachable():
    ids = [str(uuid4()) for _ in range(2500)]
    first = [discover_species(identity).rarity for identity in ids]
    assert [discover_species(identity).rarity for identity in ids] == first
    assert set(first) == set(RARITIES)


def test_locked_location_and_unequipped_grass_rejected(session_factory):
    db, player = make_player(session_factory)
    snapshot = world_snapshot(db, player, 1, set())
    assert len(snapshot['locations']) == 7  # secrets not leaked before discovery
    assert not next(item for item in snapshot['locations'] if item['code'] == 'neighborhood')['unlocked']
    try:
        select_location(db, player, 'neighborhood', 1, set())
        assert False, 'level gate did not stop travel'
    except ValueError:
        pass
    try:
        select_grass(db, player, 'cosmic_admin')
        assert False, 'missing collection item was equipped'
    except ValueError:
        pass
    assert select_location(db, player, 'neighborhood', 2, set()) == 'neighborhood'
    assert select_grass(db, player, 'meadow') == 'meadow'
    db.close()


def test_discovery_is_idempotent_and_capped_at_three_per_utc_day(session_factory):
    db, player = make_player(session_factory)
    finds = []
    for i in range(5):
        _, finished = play(db, player, NOW + timedelta(minutes=3 * i), 65)
        finds.append(finished['new_plant'])
        if i == 0:
            retried = finish_session(db, player.id, finished['session']['id'], NOW + timedelta(seconds=9))
            assert retried['new_plant'] is None
            assert retried['player']['sessions_completed'] == 1
    assert sum(value is not None for value in finds) == 3
    assert sum(collection(db, player.id).values()) == 3
    assert db.scalar(select(func.count()).select_from(GrassUnlock)) <= 3
    assert db.get(Player, player.id).sessions_completed == 5
    db.close()


def test_daily_rewards_are_once_only_and_never_client_supplied(session_factory):
    db, player = make_player(session_factory)
    receipt, finished = play(db, player, NOW, 80)
    assert receipt['granted'] == 80
    assert finished['new_plant'] is not None
    daily = daily_snapshot(db, player, NOW + timedelta(seconds=10))
    assert [item['code'] for item in daily['quests'] if item['completed']] == ['TOUCH_80', 'FIND_GRASS']
    first = claim_daily(db, player, 'TOUCH_80', NOW + timedelta(seconds=11))
    second = claim_daily(db, player, 'TOUCH_80', NOW + timedelta(seconds=12))
    assert first['xp_granted'] == 35 and not first['already_claimed']
    assert second['xp_granted'] == 0 and second['already_claimed']
    assert db.get(Player, player.id).xp == 115
    assert db.scalar(select(func.count()).select_from(DailyClaim)) == 1
    db.close()


def test_utc_day_and_week_leaderboards_use_accepted_receipts(session_factory):
    db, alice = make_player(session_factory, 301)
    bob = Player(id=302, first_name='Bob', recent_jokes=[])
    db.add(bob)
    db.commit()
    play(db, alice, NOW - timedelta(days=1), 60) # previous day, same ISO week
    play(db, alice, NOW, 40)
    play(db, bob, NOW + timedelta(minutes=1), 70)
    daily = leaderboard(db, 'day', NOW + timedelta(minutes=3))
    weekly = leaderboard(db, 'week', NOW + timedelta(minutes=3))
    assert [(r['id'], r['touches']) for r in daily['leaders']] == [('302', 70), ('301', 40)]
    assert [(r['id'], r['touches']) for r in weekly['leaders']] == [('301', 100), ('302', 70)]
    assert daily['starts_at'].startswith('2026-09-26')
    assert weekly['starts_at'].startswith('2026-09-21')
    assert daily_snapshot(db, alice, NOW)['quests'][0]['progress'] == 40
    db.close()


def test_soft_streak_preserves_one_gap_and_long_term_record(session_factory):
    _, player = make_player(session_factory)
    record_activity(player, NOW)
    record_activity(player, NOW + timedelta(days=1))
    record_activity(player, NOW + timedelta(days=3)) # one missed day
    assert player.activity_streak == 2
    record_activity(player, NOW + timedelta(days=4))
    assert player.activity_streak == 3
    record_activity(player, NOW + timedelta(days=9))
    assert player.activity_streak == 1 and player.best_streak == 3


def test_five_species_and_location_selection_persist(session_factory):
    db, player = make_player(session_factory)
    player.xp = 1000
    assert level_for_xp(player.xp) == 5
    for code in list(SPECIES)[:5]:
        db.add(GrassUnlock(player_id=player.id, species_code=code, copies=1, first_found_at=NOW))
    db.commit()
    code = list(SPECIES)[2]
    assert select_grass(db, player, code) == code
    assert select_location(db, player, 'garden_404', 5, {'GRASS_1000'}) == 'garden_404'
    db.expire_all()
    assert db.get(Player, player.id).selected_grass == code
    assert db.get(Player, player.id).selected_location == 'garden_404'
    db.close()


def test_friday_mythic_plant_is_only_possible_on_real_friday(session_factory, monkeypatch):
    import backend.app.progress as progress
    db, player = make_player(session_factory, 901)
    monkeypatch.setattr(progress, 'discover_species', lambda _session: SPECIES['friday_success'])
    _, saturday = play(db, player, NOW, 60)
    assert saturday['new_plant']['code'] == 'cosmic_admin'
    friday = NOW - timedelta(days=1)
    _, short_friday = play(db, player, friday, 60)
    assert short_friday['new_plant']['code'] == 'cosmic_admin'
    _, long_friday = play(db, player, friday + timedelta(hours=1), 100)
    assert long_friday['new_plant']['code'] == 'friday_success'
    assert 'FRIDAY_DEPLOY' in long_friday['new_achievements']
    db.close()
