class FakeEspnPlayer:
    def __init__(self, playerId, name, position, proTeam,
                 injuryStatus="ACTIVE", projected_total_points=0.0,
                 total_points=0.0):
        self.playerId = playerId
        self.name = name
        self.position = position
        self.proTeam = proTeam
        self.injuryStatus = injuryStatus
        self.projected_total_points = projected_total_points
        self.total_points = total_points


class FakeEspnTeam:
    def __init__(self, team_id, team_name, wins, losses, ties,
                 points_for, points_against, roster):
        self.team_id = team_id
        self.team_name = team_name
        self.wins = wins
        self.losses = losses
        self.ties = ties
        self.points_for = points_for
        self.points_against = points_against
        self.roster = roster


class FakeEspnLeague:
    def __init__(self, teams, free_agents=None, current_week=1):
        self.teams = teams
        self._free_agents = free_agents or []
        self.current_week = current_week

    def free_agents(self, size=100, position=None):
        return self._free_agents[:size]
