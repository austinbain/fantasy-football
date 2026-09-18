import random
from dataclasses import dataclass

from app.models import Matchup, Team


@dataclass
class TeamPowerRanking:
    team_id: int
    team_name: str
    power_score: float
    rank: int
    luck_index: float
    strength_of_schedule: float


@dataclass
class StandingsProjection:
    team_id: int
    team_name: str
    projected_wins: float
    projected_losses: float


def _win_pct(team: Team) -> float:
    games = team.wins + team.losses + team.ties
    return team.wins / games if games else 0.0


def _strength_of_schedule(session, team: Team, season_year: int,
                           teams_by_id: dict) -> float:
    matchups = (
        session.query(Matchup)
        .filter(Matchup.season == season_year)
        .filter((Matchup.home_team_id == team.id)
                | (Matchup.away_team_id == team.id))
        .all()
    )
    if not matchups:
        return 0.5

    opponent_win_pcts = []
    for matchup in matchups:
        opponent_id = (matchup.away_team_id if matchup.home_team_id == team.id
                       else matchup.home_team_id)
        opponent = teams_by_id.get(opponent_id)
        if opponent is not None:
            opponent_win_pcts.append(_win_pct(opponent))

    return sum(opponent_win_pcts) / len(opponent_win_pcts) if opponent_win_pcts else 0.5


def compute_power_rankings(session, season_year: int) -> list[TeamPowerRanking]:
    teams = session.query(Team).all()
    if not teams:
        return []

    teams_by_id = {team.id: team for team in teams}
    league_avg_points_for = sum(t.points_for for t in teams) / len(teams)

    scored = []
    for team in teams:
        power_score = _win_pct(team) * 0.5 + (
            team.points_for / league_avg_points_for if league_avg_points_for else 1.0
        ) * 0.5
        points_for_rank = sorted(teams, key=lambda t: t.points_for,
                                  reverse=True).index(team) + 1
        expected_win_pct = 1 - (points_for_rank - 1) / max(len(teams) - 1, 1)
        luck_index = _win_pct(team) - expected_win_pct
        sos = _strength_of_schedule(session, team, season_year, teams_by_id)
        scored.append((team, power_score, luck_index, sos))

    scored.sort(key=lambda item: item[1], reverse=True)

    return [
        TeamPowerRanking(
            team_id=team.id, team_name=team.name, power_score=power_score,
            rank=idx + 1, luck_index=luck_index, strength_of_schedule=sos,
        )
        for idx, (team, power_score, luck_index, sos) in enumerate(scored)
    ]


def project_standings(session, season_year: int, remaining_weeks: int,
                       simulations: int = 1000,
                       random_seed: int | None = None) -> list[StandingsProjection]:
    rng = random.Random(random_seed)
    teams = session.query(Team).all()

    win_totals = {team.id: 0.0 for team in teams}
    for _ in range(simulations):
        for team in teams:
            games_played = team.wins + team.losses + team.ties
            avg_points = team.points_for / games_played if games_played else 100.0
            simulated_wins = 0
            for _ in range(remaining_weeks):
                simulated_score = rng.gauss(avg_points, avg_points * 0.15)
                opponent_score = rng.gauss(avg_points, avg_points * 0.15)
                if simulated_score > opponent_score:
                    simulated_wins += 1
            win_totals[team.id] += team.wins + simulated_wins

    return [
        StandingsProjection(
            team_id=team.id,
            team_name=team.name,
            projected_wins=win_totals[team.id] / simulations,
            projected_losses=(team.wins + team.losses + remaining_weeks)
            - (win_totals[team.id] / simulations),
        )
        for team in teams
    ]
