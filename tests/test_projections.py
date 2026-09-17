import pytest

from app.db import make_engine, make_session_factory
from app.models import Player, WeeklyStat, DefenseVsPosition
from app.projections import project_player


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()
    session.add(Player(id=1, name="Star RB", position="RB", pro_team="SF"))
    for week, points in [(1, 10.0), (2, 20.0), (3, 30.0)]:
        session.add(WeeklyStat(player_id=1, week=week, season=2026,
                                fantasy_points=points))
    # League-average points allowed to RBs is 15; SEA allows 30 (tough matchup for offense = allows more, i.e. weak defense)
    # Add defense data for weeks 1-3 to establish baseline league average
    for week in [1, 2, 3]:
        session.add(DefenseVsPosition(pro_team="SEA", position="RB", week=week,
                                       season=2026, points_allowed=30.0))
        session.add(DefenseVsPosition(pro_team="LAR", position="RB", week=week,
                                       season=2026, points_allowed=10.0))
        session.add(DefenseVsPosition(pro_team="KC", position="RB", week=week,
                                       season=2026, points_allowed=5.0))
    # Add week 4 data
    session.add(DefenseVsPosition(pro_team="SEA", position="RB", week=4,
                                   season=2026, points_allowed=30.0))
    session.add(DefenseVsPosition(pro_team="LAR", position="RB", week=4,
                                   season=2026, points_allowed=10.0))
    session.commit()
    yield session
    session.close()


def test_project_player_blends_season_avg_and_recent_form(session):
    projection = project_player(session, player_id=1, season_year=2026,
                                 upcoming_week=4, upcoming_opponent="LAR")
    assert projection.season_avg == pytest.approx(20.0)
    # last-3-week average with weight toward recency: (10*1 + 20*2 + 30*3) / 6 = 23.33
    assert projection.recent_form == pytest.approx(23.3333, rel=1e-3)


def test_project_player_favorable_matchup_increases_points(session):
    easy_matchup = project_player(session, player_id=1, season_year=2026,
                                   upcoming_week=4, upcoming_opponent="SEA")
    tough_matchup = project_player(session, player_id=1, season_year=2026,
                                    upcoming_week=4, upcoming_opponent="LAR")
    assert easy_matchup.points > tough_matchup.points


def test_project_player_no_defense_data_defaults_to_neutral_matchup(session):
    projection = project_player(session, player_id=1, season_year=2026,
                                 upcoming_week=4, upcoming_opponent="UNKNOWN")
    assert projection.matchup_multiplier == pytest.approx(1.0)


def test_project_player_falls_back_to_espn_projection_when_no_nflverse_stats(session):
    session.add(Player(id=2, name="No Stats Player", position="WR",
                        pro_team="DAL", espn_projected_points=12.5))
    session.commit()

    projection = project_player(session, player_id=2, season_year=2026,
                                 upcoming_week=4, upcoming_opponent="LAR")
    assert projection.points == pytest.approx(12.5)
    assert projection.matchup_multiplier == pytest.approx(1.0)
