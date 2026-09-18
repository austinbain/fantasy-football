import pandas as pd

PLAYER_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "player_stats/player_stats_{year}.parquet"
)
PLAYER_ID_CROSSWALK_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/"
    "files/db_playerids.csv"
)


def _default_weekly_data_fn(years: list[int]) -> pd.DataFrame:
    return pd.concat(
        [pd.read_parquet(PLAYER_STATS_URL.format(year=year)) for year in years],
        ignore_index=True,
    )


def _default_ids_fn() -> pd.DataFrame:
    return pd.read_csv(PLAYER_ID_CROSSWALK_URL, low_memory=False)


class StatsClient:
    def __init__(self, weekly_data_fn=None, ids_fn=None):
        self._weekly_data_fn = weekly_data_fn or _default_weekly_data_fn
        self._ids_fn = ids_fn or _default_ids_fn
        self._weekly_cache: dict[int, pd.DataFrame] = {}

    def get_weekly_stats(self, season_year: int) -> pd.DataFrame:
        if season_year not in self._weekly_cache:
            df = self._weekly_data_fn([season_year])
            self._weekly_cache[season_year] = (
                df[df["season"] == season_year].reset_index(drop=True)
            )
        return self._weekly_cache[season_year]

    def get_defense_vs_position(self, season_year: int) -> pd.DataFrame:
        weekly = self.get_weekly_stats(season_year)
        grouped = (
            weekly.groupby(["opponent_team", "position", "week"])["fantasy_points"]
            .sum()
            .reset_index()
            .rename(columns={"opponent_team": "pro_team",
                              "fantasy_points": "points_allowed"})
        )
        return grouped

    def get_player_id_crosswalk(self) -> pd.DataFrame:
        ids = self._ids_fn()
        ids = ids.dropna(subset=["espn_id"]).copy()
        ids["espn_id"] = ids["espn_id"].astype(float).astype(int).astype(str)
        return ids[["espn_id", "gsis_id", "name"]]
