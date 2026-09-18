import pandas as pd

from app.db import make_engine, make_session_factory
from app.espn_client import EspnTeam, EspnPlayer
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


def test_sync_all_matches_weekly_stats_via_name_fallback():
    """A player whose gsis_id can only be resolved via the name-fallback
    path (no matching espn_id row in the crosswalk) must still have their
    weekly stats synced under the correct ESPN player id."""

    class EspnClientWithNameFallbackPlayer:
        def get_teams(self):
            return [EspnTeam(id=1, name="Dynasty Warriors", wins=5, losses=3,
                              ties=0, points_for=650.5, points_against=600.0)]

        def get_rosters(self):
            return {1: [EspnPlayer(id=202, name="Backup WR", position="WR",
                                    pro_team="SF", injury_status="ACTIVE",
                                    team_id=1, projected_points=5.0,
                                    actual_points=20.0)]}

        def get_free_agents(self, size=100):
            return []

        @property
        def current_week(self):
            return 2

    class StatsClientWithNameFallback:
        def get_weekly_stats(self, season_year):
            return pd.DataFrame([
                {"player_id": "g2", "player_name": "Backup WR",
                 "position": "WR", "recent_team": "SF",
                 "opponent_team": "SEA", "week": 1, "fantasy_points": 14.7},
            ])

        def get_defense_vs_position(self, season_year):
            return pd.DataFrame([
                {"pro_team": "SEA", "position": "WR", "week": 1,
                 "points_allowed": 14.7},
            ])

        def get_player_id_crosswalk(self):
            # espn_id "999999" does not match any real ESPN player id, so
            # the only way to resolve this player's gsis_id is by name.
            return pd.DataFrame([
                {"espn_id": "999999", "gsis_id": "g2", "name": "Backup WR"},
            ])

    session = make_session()
    sync_all(session, EspnClientWithNameFallbackPlayer(),
             StatsClientWithNameFallback(), 2026)

    player = session.query(Player).filter_by(id=202).one()
    assert player.gsis_id == "g2"

    stat = session.query(WeeklyStat).filter_by(player_id=202).one()
    assert stat.fantasy_points == 14.7


def test_sync_all_treats_ambiguous_names_as_unmatched():
    """A name that appears more than once in the crosswalk must never be
    used as a fallback match — an ambiguous match is worse than no match."""

    class EspnClientWithAmbiguousNamePlayer:
        def get_teams(self):
            return [EspnTeam(id=1, name="Dynasty Warriors", wins=5, losses=3,
                              ties=0, points_for=650.5, points_against=600.0)]

        def get_rosters(self):
            return {1: [EspnPlayer(id=303, name="Common Name", position="WR",
                                    pro_team="SF", injury_status="ACTIVE",
                                    team_id=1, projected_points=5.0,
                                    actual_points=20.0)]}

        def get_free_agents(self, size=100):
            return []

        @property
        def current_week(self):
            return 2

    class StatsClientWithAmbiguousName:
        def get_weekly_stats(self, season_year):
            return pd.DataFrame(columns=["player_id", "player_name", "position",
                                          "recent_team", "opponent_team", "week",
                                          "fantasy_points"])

        def get_defense_vs_position(self, season_year):
            return pd.DataFrame(columns=["pro_team", "position", "week",
                                          "points_allowed"])

        def get_player_id_crosswalk(self):
            # "Common Name" appears twice with different gsis_ids -- ambiguous.
            return pd.DataFrame([
                {"espn_id": "111111", "gsis_id": "gA", "name": "Common Name"},
                {"espn_id": "222222", "gsis_id": "gB", "name": "Common Name"},
            ])

    session = make_session()
    result = sync_all(session, EspnClientWithAmbiguousNamePlayer(),
                       StatsClientWithAmbiguousName(), 2026)

    player = session.query(Player).filter_by(id=303).one()
    assert player.gsis_id is None
    assert "Common Name" in result.unmatched_players


def test_sync_all_degrades_gracefully_when_nflverse_is_unreachable():
    """nflverse being unreachable must not crash the whole sync — the ESPN
    half still completes and the failure is reported on the result."""

    class UnreachableStatsClient:
        def get_player_id_crosswalk(self):
            raise ConnectionError("simulated network failure")

        def get_weekly_stats(self, season_year):
            raise ConnectionError("simulated network failure")

        def get_defense_vs_position(self, season_year):
            raise ConnectionError("simulated network failure")

    session = make_session()
    result = sync_all(session, FakeEspnClient(), UnreachableStatsClient(), 2026)

    assert result.teams_synced == 1
    assert result.players_synced == 2
    assert result.stats_sync_error is not None
    assert "nflverse" in result.stats_sync_error.lower()

    rb = session.query(Player).filter_by(id=101).one()
    assert rb.gsis_id is None  # crosswalk never fetched, nothing to match against


def test_sync_all_records_current_week_from_espn():
    session = make_session()
    result = sync_all(session, FakeEspnClient(), FakeStatsClient(), 2026)
    assert result.current_week == 2
