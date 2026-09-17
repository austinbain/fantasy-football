import pytest

from app.db import make_engine, make_session_factory
from app.models import Player, WeeklyStat
from app.analytics.waiver import rank_waiver_wire


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()

    # My team has two RBs (adequate depth) and zero WRs (a need).
    session.add_all([
        Player(id=1, name="My RB1", position="RB", pro_team="SF", team_id=1),
        Player(id=2, name="My RB2", position="RB", pro_team="KC", team_id=1),
    ])
    # Free agents: one RB, one WR, similar raw projections.
    session.add_all([
        Player(id=10, name="FA RB", position="RB", pro_team="NYJ"),
        Player(id=11, name="FA WR", position="WR", pro_team="DAL"),
    ])
    for player_id in [1, 2, 10, 11]:
        for week in range(1, 4):
            session.add(WeeklyStat(player_id=player_id, week=week, season=2026,
                                    fantasy_points=12.0))
    session.commit()
    yield session
    session.close()


def test_rank_waiver_wire_prioritizes_need_position(session):
    ranked = rank_waiver_wire(session, team_id=1, season_year=2026, week=4)
    assert ranked[0].position == "WR"
    assert ranked[0].name == "FA WR"


def test_rank_waiver_wire_only_includes_free_agents(session):
    ranked = rank_waiver_wire(session, team_id=1, season_year=2026, week=4)
    ids = {c.player_id for c in ranked}
    assert ids == {10, 11}


def test_rank_waiver_wire_respects_limit(session):
    ranked = rank_waiver_wire(session, team_id=1, season_year=2026, week=4,
                               limit=1)
    assert len(ranked) == 1
