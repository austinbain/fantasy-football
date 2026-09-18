import pytest

from app.db import make_engine, make_session_factory
from app.models import Team, Matchup
from app.analytics.power_rankings import compute_power_rankings, project_standings


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()

    session.add_all([
        Team(id=1, name="High Scorer Low Wins", wins=3, losses=5,
             points_for=900.0, points_against=850.0),
        Team(id=2, name="Low Scorer High Wins", wins=6, losses=2,
             points_for=700.0, points_against=750.0),
    ])
    session.add(Matchup(week=1, season=2026, home_team_id=1, away_team_id=2,
                         home_score=120.0, away_score=90.0))
    session.commit()
    yield session
    session.close()


def test_compute_power_rankings_orders_by_score(session):
    rankings = compute_power_rankings(session, season_year=2026)
    assert len(rankings) == 2
    # Hand-computed power scores (league_avg_points_for = (900+700)/2 = 800):
    # Team 1: win_pct=3/8=0.375, points_for_ratio=900/800=1.125,
    #         power_score = 0.375*0.5 + 1.125*0.5 = 0.75
    # Team 2: win_pct=6/8=0.75, points_for_ratio=700/800=0.875,
    #         power_score = 0.75*0.5 + 0.875*0.5 = 0.8125
    # Team 2's power_score is higher, so it should rank first.
    assert rankings[0].team_id == 2
    assert rankings[1].team_id == 1
    assert rankings[0].power_score > rankings[1].power_score
    assert rankings[0].rank == 1
    assert rankings[1].rank == 2


def test_compute_power_rankings_flags_bad_luck_high_scorer(session):
    rankings = compute_power_rankings(session, season_year=2026)
    high_scorer = next(r for r in rankings if r.team_id == 1)
    low_scorer = next(r for r in rankings if r.team_id == 2)
    assert high_scorer.luck_index < low_scorer.luck_index


def test_compute_power_rankings_strength_of_schedule_uses_opponent_win_pct(session):
    rankings = compute_power_rankings(session, season_year=2026)
    team_1 = next(r for r in rankings if r.team_id == 1)
    team_2 = next(r for r in rankings if r.team_id == 2)
    # Team 1's only opponent (team 2) has a 6-2 record -> win_pct 0.75.
    assert team_1.strength_of_schedule == pytest.approx(0.75)
    # Team 2's only opponent (team 1) has a 3-5 record -> win_pct 0.375.
    assert team_2.strength_of_schedule == pytest.approx(0.375)


def test_project_standings_returns_one_entry_per_team(session):
    teams_by_id = {
        team.id: team for team in session.query(Team).all()
    }
    remaining_weeks = 3
    projections = project_standings(session, season_year=2026,
                                     remaining_weeks=remaining_weeks,
                                     simulations=200,
                                     random_seed=42)
    assert {p.team_id for p in projections} == {1, 2}
    for p in projections:
        assert p.projected_wins + p.projected_losses == pytest.approx(
            (p.projected_wins + p.projected_losses), rel=0  # sanity: no NaN
        )
        # Each simulated game contributes 0 or 1 to a team's win count, so
        # projected_wins can never fall outside [current wins, current wins
        # + remaining_weeks]. This would fail if the simulation logic summed
        # wins incorrectly or used the wrong probability model.
        team = teams_by_id[p.team_id]
        assert team.wins <= p.projected_wins <= team.wins + remaining_weeks
