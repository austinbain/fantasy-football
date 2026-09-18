import pytest

from app.db import make_engine, make_session_factory
from app.models import Player, WeeklyStat
from app.analytics.lineup import recommend_lineup


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()

    session.add_all([
        Player(id=1, name="QB1", position="QB", pro_team="KC", team_id=1),
        Player(id=2, name="RB1", position="RB", pro_team="SF", team_id=1),
        Player(id=3, name="RB2", position="RB", pro_team="MIA", team_id=1),
        Player(id=4, name="RB3 (bench)", position="RB", pro_team="DAL", team_id=1),
        Player(id=5, name="WR1", position="WR", pro_team="BUF", team_id=1),
        Player(id=6, name="WR2", position="WR", pro_team="CIN", team_id=1),
        Player(id=7, name="TE1", position="TE", pro_team="NYJ", team_id=1),
        Player(id=8, name="DST1", position="DST", pro_team="SEA", team_id=1),
        Player(id=9, name="K1", position="K", pro_team="LAR", team_id=1),
    ])
    # NOTE: player 4 ("RB3 (bench)") is intentionally scored lower than both
    # starting RBs (players 2 and 3). RB starting slots are filled before
    # FLEX in STANDARD_SLOTS, so if this player scored higher than the
    # starters (as an earlier fixture draft had it, at 25 points) the
    # optimizer would correctly promote it to a starting RB slot instead of
    # leaving it for FLEX -- the two RB starters must outscore it for the
    # "flex takes the best remaining player" test to exercise what it claims
    # to. With this player as the only flex-eligible player left over after
    # the RB/WR/TE starting slots are filled, it lands in FLEX regardless of
    # its exact point value, so any value below 14 (RB2's score) works.
    points = {1: 20, 2: 15, 3: 14, 4: 12, 5: 10, 6: 9, 7: 8, 8: 7, 9: 6}
    for player_id, pts in points.items():
        for week in range(1, 4):
            session.add(WeeklyStat(player_id=player_id, week=week, season=2026,
                                    fantasy_points=pts))
    session.commit()
    yield session
    session.close()


def test_recommend_lineup_fills_all_slots(session):
    lineup = recommend_lineup(session, team_id=1, season_year=2026, week=4)
    slots = [rec.slot for rec in lineup]
    assert slots == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DST", "K"]


def test_recommend_lineup_flex_takes_best_remaining_rb_wr_te(session):
    lineup = recommend_lineup(session, team_id=1, season_year=2026, week=4)
    flex = next(rec for rec in lineup if rec.slot == "FLEX")
    assert flex.player_name == "RB3 (bench)"


def test_recommend_lineup_no_player_used_twice(session):
    lineup = recommend_lineup(session, team_id=1, season_year=2026, week=4)
    player_ids = [rec.player_id for rec in lineup]
    assert len(player_ids) == len(set(player_ids))
