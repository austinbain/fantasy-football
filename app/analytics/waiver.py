from dataclasses import dataclass

from app.models import Player
from app.projections import project_player

ROSTER_NEED_TARGET = {"QB": 2, "RB": 4, "WR": 4, "TE": 2, "K": 1, "D/ST": 1}


@dataclass
class WaiverCandidate:
    player_id: int
    name: str
    position: str
    projected_points: float
    need_score: float
    combined_score: float


def _need_score(session, team_id: int, position: str) -> float:
    target = ROSTER_NEED_TARGET.get(position, 2)
    current_count = (
        session.query(Player)
        .filter_by(team_id=team_id, position=position)
        .count()
    )
    if current_count >= target:
        return 0.5
    gap = target - current_count
    return 1.0 + (gap * 0.5)


def rank_waiver_wire(session, team_id: int, season_year: int, week: int,
                      limit: int = 25) -> list[WaiverCandidate]:
    free_agents = session.query(Player).filter(Player.team_id.is_(None)).all()

    candidates = []
    for player in free_agents:
        projection = project_player(session, player.id, season_year, week,
                                     upcoming_opponent="")
        need_score = _need_score(session, team_id, player.position)
        combined = projection.points * need_score
        candidates.append(WaiverCandidate(
            player_id=player.id,
            name=player.name,
            position=player.position,
            projected_points=projection.points,
            need_score=need_score,
            combined_score=combined,
        ))

    candidates.sort(key=lambda c: c.combined_score, reverse=True)
    return candidates[:limit]
