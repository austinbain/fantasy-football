from dataclasses import dataclass

from app.models import Player
from app.projections import project_player

STANDARD_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "D/ST", "K"]
FLEX_ELIGIBLE = {"RB", "WR", "TE"}


@dataclass
class LineupRecommendation:
    slot: str
    player_id: int
    player_name: str
    projected_points: float


def recommend_lineup(session, team_id: int, season_year: int,
                      week: int) -> list[LineupRecommendation]:
    roster = session.query(Player).filter_by(team_id=team_id).all()

    scored = []
    for player in roster:
        projection = project_player(session, player.id, season_year, week,
                                     upcoming_opponent="")
        scored.append((player, projection.points))
    scored.sort(key=lambda item: item[1], reverse=True)

    used_ids: set[int] = set()
    recommendations: list[LineupRecommendation] = []

    for slot in STANDARD_SLOTS:
        if slot == "FLEX":
            eligible_positions = FLEX_ELIGIBLE
        else:
            eligible_positions = {slot}

        best = next(
            (item for item in scored
             if item[0].position in eligible_positions
             and item[0].id not in used_ids),
            None,
        )
        if best is None:
            continue
        player, points = best
        used_ids.add(player.id)
        recommendations.append(LineupRecommendation(
            slot=slot, player_id=player.id, player_name=player.name,
            projected_points=points,
        ))

    return recommendations
