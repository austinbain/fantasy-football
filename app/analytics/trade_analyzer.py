from dataclasses import dataclass

from app.models import Player, Team
from app.projections import project_player

POSITION_SCARCITY = {
    "QB": 0.9, "RB": 1.15, "WR": 1.05, "TE": 1.1, "K": 0.7, "DST": 0.7,
}


@dataclass
class TradeSide:
    team_id: int
    player_ids: list[int]


@dataclass
class TradeEvaluation:
    side_a_value: float
    side_b_value: float
    difference_pct: float
    is_lopsided: bool


@dataclass
class TradeSuggestion:
    give_player_id: int
    get_player_id: int
    other_team_id: int
    rationale: str


def _player_value(session, player_id: int, season_year: int, week: int) -> float:
    player = session.get(Player, player_id)
    projection = project_player(session, player_id, season_year, week,
                                 upcoming_opponent="")
    scarcity = POSITION_SCARCITY.get(player.position, 1.0)
    return projection.points * scarcity


def _side_value(session, side: TradeSide, season_year: int, week: int) -> float:
    return sum(_player_value(session, pid, season_year, week)
               for pid in side.player_ids)


def evaluate_trade(session, side_a: TradeSide, side_b: TradeSide,
                    season_year: int, week: int,
                    threshold_pct: float = 0.2) -> TradeEvaluation:
    value_a = _side_value(session, side_a, season_year, week)
    value_b = _side_value(session, side_b, season_year, week)
    larger = max(value_a, value_b)
    smaller = min(value_a, value_b)
    difference_pct = (larger - smaller) / larger if larger else 0.0

    return TradeEvaluation(
        side_a_value=value_a,
        side_b_value=value_b,
        difference_pct=difference_pct,
        is_lopsided=difference_pct > threshold_pct,
    )


def _roster_by_position(session, team_id: int) -> dict[str, list[Player]]:
    players = session.query(Player).filter_by(team_id=team_id).all()
    by_position: dict[str, list[Player]] = {}
    for p in players:
        by_position.setdefault(p.position, []).append(p)
    return by_position


def suggest_trades(session, my_team_id: int, season_year: int, week: int,
                    max_suggestions: int = 5) -> list[TradeSuggestion]:
    my_roster = _roster_by_position(session, my_team_id)
    other_teams = session.query(Team).filter(Team.id != my_team_id).all()

    suggestions = []
    for position, my_players in my_roster.items():
        if len(my_players) < 2:
            continue
        my_players_sorted = sorted(
            my_players,
            key=lambda p: _player_value(session, p.id, season_year, week),
            reverse=True,
        )
        surplus_player = my_players_sorted[-1]

        for other_team in other_teams:
            other_roster = _roster_by_position(session, other_team.id)
            candidates = other_roster.get(position, [])
            if not candidates:
                continue
            best_candidate = max(
                candidates,
                key=lambda p: _player_value(session, p.id, season_year, week),
            )
            if _player_value(session, best_candidate.id, season_year, week) > \
               _player_value(session, surplus_player.id, season_year, week):
                suggestions.append(TradeSuggestion(
                    give_player_id=surplus_player.id,
                    get_player_id=best_candidate.id,
                    other_team_id=other_team.id,
                    rationale=(
                        f"Your depth {position} ({surplus_player.name}) for "
                        f"their stronger {position} ({best_candidate.name})"
                    ),
                ))
            if len(suggestions) >= max_suggestions:
                return suggestions
    return suggestions
