import pytest
from fastapi.testclient import TestClient

from app.db import make_engine, make_session_factory
from app.models import Player, WeeklyStat
from app.web.app import create_app


@pytest.fixture
def client():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    session = session_factory()
    session.add(Player(id=1, name="FA Player", position="RB", pro_team="SF"))
    for week in range(1, 4):
        session.add(WeeklyStat(player_id=1, week=week, season=2026,
                                fantasy_points=15.0))
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


def test_waiver_page_lists_ranked_free_agents(client):
    response = client.get("/waiver")
    assert response.status_code == 200
    assert "FA Player" in response.text
