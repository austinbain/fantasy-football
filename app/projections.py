from dataclasses import dataclass

from app.models import WeeklyStat, DefenseVsPosition, Player


@dataclass
class Projection:
    player_id: int
    points: float
    season_avg: float
    recent_form: float
    matchup_multiplier: float


def _weighted_recent_form(points_by_week: list[float]) -> float:
    recent = points_by_week[-3:]
    weights = list(range(1, len(recent) + 1))
    return sum(p * w for p, w in zip(recent, weights)) / sum(weights)


def _matchup_multiplier(session, position: str, opponent: str,
                         season_year: int, upcoming_week: int) -> float:
    all_rows = (
        session.query(DefenseVsPosition)
        .filter_by(position=position, season=season_year)
        .filter(DefenseVsPosition.week <= upcoming_week)
        .all()
    )
    if not all_rows:
        return 1.0
    league_avg = sum(r.points_allowed for r in all_rows) / len(all_rows)
    if league_avg == 0:
        return 1.0
    opponent_rows = [r for r in all_rows if r.pro_team == opponent]
    if not opponent_rows:
        return 1.0
    opponent_avg = sum(r.points_allowed for r in opponent_rows) / len(opponent_rows)
    return opponent_avg / league_avg


def project_player(session, player_id: int, season_year: int,
                    upcoming_week: int, upcoming_opponent: str) -> Projection:
    player = session.get(Player, player_id)
    stats = (
        session.query(WeeklyStat)
        .filter_by(player_id=player_id, season=season_year)
        .filter(WeeklyStat.week < upcoming_week)
        .order_by(WeeklyStat.week)
        .all()
    )
    points_by_week = [s.fantasy_points for s in stats]

    if not points_by_week:
        # No nflverse-sourced weekly stats yet (early season, sync gap, or a
        # player nflverse doesn't track) — fall back to ESPN's own
        # projection with a neutral matchup adjustment rather than a bogus 0.
        fallback = player.espn_projected_points or 0.0
        return Projection(player_id=player_id, points=fallback,
                           season_avg=fallback, recent_form=fallback,
                           matchup_multiplier=1.0)

    season_avg = sum(points_by_week) / len(points_by_week)
    recent_form = _weighted_recent_form(points_by_week)
    multiplier = _matchup_multiplier(session, player.position, upcoming_opponent,
                                      season_year, upcoming_week)

    base = season_avg * 0.4 + recent_form * 0.6
    points = base * multiplier

    return Projection(player_id=player_id, points=points, season_avg=season_avg,
                       recent_form=recent_form, matchup_multiplier=multiplier)
