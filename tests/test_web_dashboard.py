import pytest
from fastapi.testclient import TestClient

from app.db import make_engine, make_session_factory
from app.models import Team
from app.web.app import create_app


class FakeEspnClient:
    def get_teams(self):
        return []

    def get_rosters(self):
        return {}

    def get_free_agents(self, size=100):
        return []

    @property
    def current_week(self):
        return 1


class FakeStatsClient:
    def get_weekly_stats(self, season_year):
        import pandas as pd
        return pd.DataFrame(columns=["player_id", "player_name", "position",
                                      "recent_team", "opponent_team", "week",
                                      "fantasy_points"])

    def get_defense_vs_position(self, season_year):
        import pandas as pd
        return pd.DataFrame(columns=["pro_team", "position", "week",
                                      "points_allowed"])

    def get_player_id_crosswalk(self):
        import pandas as pd
        return pd.DataFrame(columns=["espn_id", "gsis_id", "name"])


@pytest.fixture
def client():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    session = session_factory()
    session.add(Team(id=1, name="My Team", wins=1, losses=0, points_for=100.0,
                      points_against=80.0))
    session.commit()
    session.close()

    app = create_app(
        session_factory=session_factory,
        espn_client_factory=lambda: FakeEspnClient(),
        stats_client_factory=lambda: FakeStatsClient(),
        season_year=2026,
        my_team_id=1,
    )
    return TestClient(app)


def test_dashboard_page_loads_and_lists_teams(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "My Team" in response.text


def test_refresh_triggers_sync_and_returns_partial(client):
    response = client.post("/sync")
    assert response.status_code == 200
    assert "Synced" in response.text
