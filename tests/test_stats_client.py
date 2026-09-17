import pandas as pd

from app.stats_client import StatsClient


def fake_weekly_data_fn(years):
    return pd.DataFrame([
        {"player_id": "g1", "player_name": "Star RB", "position": "RB",
         "recent_team": "SF", "opponent_team": "SEA", "week": 1,
         "fantasy_points": 22.4, "season": 2026},
        {"player_id": "g2", "player_name": "Other RB", "position": "RB",
         "recent_team": "LAR", "opponent_team": "SEA", "week": 1,
         "fantasy_points": 10.1, "season": 2026},
        {"player_id": "g3", "player_name": "Star WR", "position": "WR",
         "recent_team": "MIA", "opponent_team": "BUF", "week": 1,
         "fantasy_points": 15.0, "season": 2026},
    ])


def fake_ids_fn():
    # Mirrors the real dynastyprocess CSV: espn_id arrives as a float.
    return pd.DataFrame([
        {"espn_id": 101.0, "gsis_id": "g1", "name": "Star RB"},
        {"espn_id": 102.0, "gsis_id": "g3", "name": "Star WR"},
        {"espn_id": float("nan"), "gsis_id": "g4", "name": "No ESPN Mapping"},
    ])


def test_get_weekly_stats_filters_by_season():
    client = StatsClient(weekly_data_fn=fake_weekly_data_fn, ids_fn=fake_ids_fn)
    df = client.get_weekly_stats(2026)
    assert set(df["player_name"]) == {"Star RB", "Other RB", "Star WR"}
    assert "fantasy_points" in df.columns


def test_get_defense_vs_position_aggregates_points_allowed():
    client = StatsClient(weekly_data_fn=fake_weekly_data_fn, ids_fn=fake_ids_fn)
    dvp = client.get_defense_vs_position(2026)
    seattle_rb_row = dvp[(dvp["pro_team"] == "SEA") & (dvp["position"] == "RB")
                         & (dvp["week"] == 1)].iloc[0]
    assert seattle_rb_row["points_allowed"] == 22.4 + 10.1


def test_get_player_id_crosswalk_normalizes_espn_id_to_string():
    client = StatsClient(weekly_data_fn=fake_weekly_data_fn, ids_fn=fake_ids_fn)
    crosswalk = client.get_player_id_crosswalk()
    row = crosswalk[crosswalk["espn_id"] == "101"].iloc[0]
    assert row["gsis_id"] == "g1"


def test_get_player_id_crosswalk_drops_rows_with_no_espn_id():
    client = StatsClient(weekly_data_fn=fake_weekly_data_fn, ids_fn=fake_ids_fn)
    crosswalk = client.get_player_id_crosswalk()
    assert "g4" not in set(crosswalk["gsis_id"])
