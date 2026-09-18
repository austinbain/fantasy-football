import pytest
from fastapi.testclient import TestClient

from app.db import make_engine, make_session_factory
from app.models import Team
from app.web.app import create_app


@pytest.fixture
def client():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    session = session_factory()
    session.add_all([
        Team(id=1, name="Team A", wins=5, losses=2, points_for=700.0,
             points_against=650.0),
        Team(id=2, name="Team B", wins=3, losses=4, points_for=650.0,
             points_against=680.0),
    ])
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


def test_analytics_page_shows_power_rankings_and_standings(client):
    response = client.get("/analytics")
    assert response.status_code == 200
    assert "Team A" in response.text
    assert "Team B" in response.text
