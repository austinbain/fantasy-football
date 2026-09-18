import pytest
from fastapi.testclient import TestClient

from app.db import make_engine, make_session_factory
from app.models import Team, Player, WeeklyStat
from app.web.app import create_app


@pytest.fixture
def client():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    session = session_factory()
    session.add_all([
        Team(id=1, name="My Team"),
        Team(id=2, name="Rival Team"),
        Player(id=1, name="Great RB", position="RB", pro_team="SF", team_id=1),
        Player(id=2, name="Great WR", position="WR", pro_team="MIA", team_id=2),
    ])
    for player_id, points in {1: 25.0, 2: 24.0}.items():
        for week in range(1, 4):
            session.add(WeeklyStat(player_id=player_id, week=week, season=2026,
                                    fantasy_points=points))
    session.commit()
    session.close()

    app = create_app(
        session_factory=session_factory,
        espn_client_factory=lambda: None,
        stats_client_factory=lambda: None,
        season_year=2026,
        my_team_id=1,
    )
    return TestClient(app)


def test_trades_page_loads_with_team_rosters(client):
    response = client.get("/trades")
    assert response.status_code == 200
    assert "Great RB" in response.text
    assert "Great WR" in response.text


def test_evaluate_trade_endpoint_returns_result_partial(client):
    response = client.post("/trades/evaluate", data={
        "side_a_players": ["1"],
        "side_b_players": ["2"],
        "week": "4",
    })
    assert response.status_code == 200
    assert "Great RB" in response.text or "value" in response.text.lower()


def test_evaluate_trade_endpoint_with_empty_side_returns_friendly_error(client):
    response = client.post("/trades/evaluate", data={
        "week": "4",
    })
    assert response.status_code == 200
    assert "select at least one player" in response.text.lower()


def test_evaluate_trade_endpoint_with_unknown_player_id_returns_friendly_error(client):
    response = client.post("/trades/evaluate", data={
        "side_a_players": ["1"],
        "side_b_players": ["999999"],
        "week": "4",
    })
    assert response.status_code == 200
    assert "could not be found" in response.text.lower()


def test_evaluate_trade_endpoint_with_malformed_player_id_returns_friendly_error(client):
    response = client.post("/trades/evaluate", data={
        "side_a_players": ["1"],
        "side_b_players": ["not-a-number"],
        "week": "4",
    })
    assert response.status_code == 200
    assert "could not be found" in response.text.lower()
