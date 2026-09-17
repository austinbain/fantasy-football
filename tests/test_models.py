import pytest
from sqlalchemy.exc import IntegrityError

from app.db import make_engine, make_session_factory
from app.models import Team, Player, WeeklyStat, DefenseVsPosition


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()
    yield session
    session.close()


def test_create_team_and_player(session):
    team = Team(id=1, name="Dynasty Warriors", wins=5, losses=3, ties=0,
                points_for=650.5, points_against=600.0)
    session.add(team)
    session.commit()

    player = Player(id=100, name="Test Player", position="RB",
                     pro_team="KC", team_id=team.id)
    session.add(player)
    session.commit()

    fetched = session.query(Player).filter_by(id=100).one()
    assert fetched.team.name == "Dynasty Warriors"


def test_free_agent_has_null_team(session):
    player = Player(id=200, name="Free Agent", position="WR", pro_team="MIA")
    session.add(player)
    session.commit()

    fetched = session.query(Player).filter_by(id=200).one()
    assert fetched.team_id is None


def test_weekly_stat_unique_constraint(session):
    player = Player(id=300, name="Stat Player", position="QB", pro_team="BUF")
    session.add(player)
    session.commit()

    session.add(WeeklyStat(player_id=300, week=1, season=2026,
                            fantasy_points=20.5))
    session.commit()

    session.add(WeeklyStat(player_id=300, week=1, season=2026,
                            fantasy_points=99.0))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_defense_vs_position_unique_constraint(session):
    session.add(DefenseVsPosition(pro_team="SF", position="RB", week=1,
                                   season=2026, points_allowed=12.3))
    session.commit()

    session.add(DefenseVsPosition(pro_team="SF", position="RB", week=1,
                                   season=2026, points_allowed=99.0))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
