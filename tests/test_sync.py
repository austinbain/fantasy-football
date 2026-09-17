import pandas as pd

from app.db import make_engine, make_session_factory
from app.espn_client import EspnClient, EspnTeam, EspnPlayer
from app.models import Player, WeeklyStat, DefenseVsPosition
from app.sync import sync_all


class FakeEspnClient:
    def get_teams(self):
        return [EspnTeam(id=1, name="Dynasty Warriors", wins=5, losses=3,
                          ties=0, points_for=650.5, points_against=600.0)]

    def get_rosters(self):
        return {1: [EspnPlayer(id=101, name="Star RB", position="RB",
                                pro_team="SF", injury_status="ACTIVE",
                                team_id=1, projected_points=18.2,
                                actual_points=150.0)]}

    def get_free_agents(self, size=100):
        return [EspnPlayer(id=999, name="Waiver Guy", position="TE",
                            pro_team="NYJ", injury_status="ACTIVE",
                            team_id=None, projected_points=5.0,
                            actual_points=10.0)]

    @property
    def current_week(self):
        return 2


class FakeStatsClient:
    def get_weekly_stats(self, season_year):
        return pd.DataFrame([
            {"player_id": "g1", "player_name": "Star RB", "position": "RB",
             "recent_team": "SF", "opponent_team": "SEA", "week": 1,
             "fantasy_points": 22.4},
        ])

    def get_defense_vs_position(self, season_year):
        return pd.DataFrame([
            {"pro_team": "SEA", "position": "RB", "week": 1,
             "points_allowed": 22.4},
        ])

    def get_player_id_crosswalk(self):
        return pd.DataFrame([
            {"espn_id": "101", "gsis_id": "g1", "name": "Star RB"},
        ])


def make_session():
    engine = make_engine(":memory:")
    return make_session_factory(engine)()


def test_sync_all_creates_teams_players_and_stats():
    session = make_session()
    result = sync_all(session, FakeEspnClient(), FakeStatsClient(), 2026)

    assert result.teams_synced == 1
    assert result.players_synced == 2
    assert result.weekly_stats_synced == 1

    rb = session.query(Player).filter_by(id=101).one()
    assert rb.gsis_id == "g1"
    assert rb.team_id == 1
    assert rb.espn_projected_points == 18.2

    fa = session.query(Player).filter_by(id=999).one()
    assert fa.team_id is None

    stat = session.query(WeeklyStat).filter_by(player_id=101).one()
    assert stat.fantasy_points == 22.4

    dvp = session.query(DefenseVsPosition).filter_by(pro_team="SEA").one()
    assert dvp.points_allowed == 22.4


def test_sync_all_reports_unmatched_players():
    session = make_session()
    result = sync_all(session, FakeEspnClient(), FakeStatsClient(), 2026)
    assert "Waiver Guy" in result.unmatched_players


def test_sync_all_is_idempotent():
    session = make_session()
    sync_all(session, FakeEspnClient(), FakeStatsClient(), 2026)
    result = sync_all(session, FakeEspnClient(), FakeStatsClient(), 2026)
    assert result.teams_synced == 1
    assert session.query(Player).count() == 2
