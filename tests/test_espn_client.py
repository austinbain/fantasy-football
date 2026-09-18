from app.espn_client import EspnClient
from tests.fixtures.espn_fake import FakeEspnLeague, FakeEspnTeam, FakeEspnPlayer


def make_fake_league():
    rb = FakeEspnPlayer(101, "Star RB", "RB", "SF",
                         projected_avg_points=18.2, total_points=150.0)
    wr = FakeEspnPlayer(102, "Star WR", "WR", "MIA",
                         projected_avg_points=14.5, total_points=120.0)
    fa = FakeEspnPlayer(999, "Waiver Guy", "TE", "NYJ",
                         projected_avg_points=5.0, total_points=10.0)
    team = FakeEspnTeam(1, "Dynasty Warriors", 5, 3, 0, 650.5, 600.0,
                         roster=[rb, wr])
    return FakeEspnLeague(teams=[team], free_agents=[fa], current_week=3)


def test_get_teams_maps_fields():
    client = EspnClient(make_fake_league())
    teams = client.get_teams()
    assert len(teams) == 1
    assert teams[0].id == 1
    assert teams[0].name == "Dynasty Warriors"
    assert teams[0].wins == 5
    assert teams[0].points_for == 650.5


def test_get_rosters_keyed_by_team_id():
    client = EspnClient(make_fake_league())
    rosters = client.get_rosters()
    assert set(rosters.keys()) == {1}
    names = {p.name for p in rosters[1]}
    assert names == {"Star RB", "Star WR"}
    rb = next(p for p in rosters[1] if p.name == "Star RB")
    assert rb.team_id == 1
    assert rb.projected_points == 18.2


def test_get_free_agents_have_no_team_id():
    client = EspnClient(make_fake_league())
    free_agents = client.get_free_agents()
    assert len(free_agents) == 1
    assert free_agents[0].name == "Waiver Guy"
    assert free_agents[0].team_id is None


def test_current_week():
    client = EspnClient(make_fake_league())
    assert client.current_week == 3
