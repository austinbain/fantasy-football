import math
from dataclasses import dataclass, field

from app.models import Team, Player, WeeklyStat, DefenseVsPosition


@dataclass
class SyncResult:
    teams_synced: int = 0
    players_synced: int = 0
    weekly_stats_synced: int = 0
    unmatched_players: list = field(default_factory=list)
    current_week: int = 1
    stats_sync_error: str | None = None


def _clean_float(value) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def _upsert_team(session, espn_team) -> Team:
    team = session.get(Team, espn_team.id)
    if team is None:
        team = Team(id=espn_team.id)
        session.add(team)
    team.name = espn_team.name
    team.wins = espn_team.wins
    team.losses = espn_team.losses
    team.ties = espn_team.ties
    team.points_for = espn_team.points_for
    team.points_against = espn_team.points_against
    return team


def _upsert_player(session, espn_player, gsis_by_espn_id: dict) -> Player:
    player = session.get(Player, espn_player.id)
    if player is None:
        player = Player(id=espn_player.id)
        session.add(player)
    player.name = espn_player.name
    player.position = espn_player.position
    player.pro_team = espn_player.pro_team
    player.injury_status = espn_player.injury_status
    player.team_id = espn_player.team_id
    player.gsis_id = gsis_by_espn_id.get(str(espn_player.id))
    player.espn_projected_points = espn_player.projected_points
    return player


def sync_all(session, espn_client, stats_client, season_year: int) -> SyncResult:
    result = SyncResult()
    result.current_week = espn_client.current_week

    for espn_team in espn_client.get_teams():
        _upsert_team(session, espn_team)
        result.teams_synced += 1
    session.commit()

    gsis_by_espn_id = {}
    gsis_by_name = {}
    try:
        crosswalk = stats_client.get_player_id_crosswalk()
        gsis_by_espn_id = dict(zip(crosswalk["espn_id"], crosswalk["gsis_id"]))
        # Only fall back to a name match when that name is unambiguous in the
        # crosswalk — a duplicate name would otherwise silently resolve to
        # whichever row happened to be written last.
        name_counts = crosswalk["name"].value_counts()
        unambiguous_names = set(name_counts[name_counts == 1].index)
        gsis_by_name = {
            name: gsis_id
            for name, gsis_id in zip(crosswalk["name"], crosswalk["gsis_id"])
            if name in unambiguous_names
        }
    except Exception as exc:
        result.stats_sync_error = (
            f"Could not fetch nflverse player data ({type(exc).__name__}: {exc}). "
            "Player projections will use ESPN's own numbers until this resolves."
        )

    all_espn_players = []
    for roster in espn_client.get_rosters().values():
        all_espn_players.extend(roster)
    all_espn_players.extend(espn_client.get_free_agents())

    for espn_player in all_espn_players:
        player = _upsert_player(session, espn_player, gsis_by_espn_id)
        if player.gsis_id is None:
            fallback = gsis_by_name.get(espn_player.name)
            if fallback:
                player.gsis_id = fallback
            else:
                result.unmatched_players.append(espn_player.name)
        result.players_synced += 1
    session.commit()

    if result.stats_sync_error is None:
        try:
            gsis_to_espn_id = {
                p.gsis_id: p.id
                for p in session.query(Player).filter(Player.gsis_id.isnot(None))
            }
            weekly = stats_client.get_weekly_stats(season_year)
            for _, row in weekly.iterrows():
                espn_id = gsis_to_espn_id.get(row["player_id"])
                if espn_id is None:
                    continue
                player_id = int(espn_id)
                existing = (
                    session.query(WeeklyStat)
                    .filter_by(player_id=player_id, week=int(row["week"]),
                               season=season_year)
                    .one_or_none()
                )
                if existing is None:
                    existing = WeeklyStat(player_id=player_id, week=int(row["week"]),
                                           season=season_year)
                    session.add(existing)
                existing.fantasy_points = _clean_float(row["fantasy_points"])
                opponent = row.get("opponent_team")
                existing.opponent_pro_team = opponent if isinstance(opponent, str) else None
                result.weekly_stats_synced += 1
            session.commit()

            dvp_df = stats_client.get_defense_vs_position(season_year)
            for _, row in dvp_df.iterrows():
                existing = (
                    session.query(DefenseVsPosition)
                    .filter_by(pro_team=row["pro_team"], position=row["position"],
                               week=int(row["week"]), season=season_year)
                    .one_or_none()
                )
                if existing is None:
                    existing = DefenseVsPosition(
                        pro_team=row["pro_team"], position=row["position"],
                        week=int(row["week"]), season=season_year,
                    )
                    session.add(existing)
                existing.points_allowed = _clean_float(row["points_allowed"])
            session.commit()
        except Exception as exc:
            result.stats_sync_error = (
                f"Could not fetch nflverse weekly stats ({type(exc).__name__}: {exc}). "
                "Player projections will use ESPN's own numbers until this resolves."
            )

    return result
