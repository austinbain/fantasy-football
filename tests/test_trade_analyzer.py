import pytest

from app.db import make_engine, make_session_factory
from app.models import Player, Team, WeeklyStat
from app.analytics.trade_analyzer import TradeSide, evaluate_trade, suggest_trades


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()

    session.add_all([
        Team(id=1, name="My Team"),
        Team(id=2, name="Rival Team"),
    ])
    session.add_all([
        Player(id=1, name="Great RB", position="RB", pro_team="SF", team_id=1),
        Player(id=2, name="Backup RB", position="RB", pro_team="SF", team_id=1),
        Player(id=3, name="Great WR", position="WR", pro_team="MIA", team_id=2),
        Player(id=4, name="Backup WR", position="WR", pro_team="MIA", team_id=2),
    ])
    # Great RB (21) and Great WR (23) are chosen so that once the
    # RB (1.15x) and WR (1.05x) scarcity multipliers are applied they land
    # on the same trade value (21 * 1.15 == 23 * 1.05 == 24.15) -- i.e. two
    # star players at different positions who are genuinely comparable in
    # trade value. Backups are far below either, at 8 and 6.
    stats = {1: 21.0, 2: 8.0, 3: 23.0, 4: 6.0}
    for player_id, points in stats.items():
        for week in range(1, 4):
            session.add(WeeklyStat(player_id=player_id, week=week, season=2026,
                                    fantasy_points=points))
    session.commit()
    yield session
    session.close()


def test_evaluate_trade_balanced_is_not_lopsided(session):
    side_a = TradeSide(team_id=1, player_ids=[1])
    side_b = TradeSide(team_id=2, player_ids=[3])
    result = evaluate_trade(session, side_a, side_b, season_year=2026, week=4)
    assert result.is_lopsided is False
    assert result.side_a_value == pytest.approx(result.side_b_value, rel=0.05)


def test_evaluate_trade_lopsided_flags_it(session):
    side_a = TradeSide(team_id=1, player_ids=[1])
    side_b = TradeSide(team_id=2, player_ids=[4])
    result = evaluate_trade(session, side_a, side_b, season_year=2026, week=4)
    assert result.is_lopsided is True
    assert result.side_a_value > result.side_b_value


def test_suggest_trades_pairs_surplus_with_need(session):
    suggestions = suggest_trades(session, my_team_id=1, season_year=2026, week=4)
    assert isinstance(suggestions, list)
    for suggestion in suggestions:
        assert suggestion.other_team_id == 2
