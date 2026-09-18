from dataclasses import dataclass


class EspnAuthError(Exception):
    pass


@dataclass
class EspnPlayer:
    id: int
    name: str
    position: str
    pro_team: str
    injury_status: str
    team_id: int | None
    projected_points: float
    actual_points: float


@dataclass
class EspnTeam:
    id: int
    name: str
    wins: int
    losses: int
    ties: int
    points_for: float
    points_against: float


def _map_player(raw_player, team_id: int | None) -> EspnPlayer:
    raw_injury_status = getattr(raw_player, "injuryStatus", "ACTIVE")
    return EspnPlayer(
        id=raw_player.playerId,
        name=raw_player.name,
        position=raw_player.position,
        pro_team=raw_player.proTeam,
        # espn_api returns [] (not a string) for players with no injury
        # designation at all, e.g. team defenses (D/ST) - never store that
        # in the DB's injury_status text column.
        injury_status=raw_injury_status if isinstance(raw_injury_status, str) else "ACTIVE",
        team_id=team_id,
        projected_points=getattr(raw_player, "projected_avg_points", 0.0),
        actual_points=getattr(raw_player, "total_points", 0.0),
    )


class EspnClient:
    def __init__(self, league):
        self._league = league

    @classmethod
    def connect(cls, league_id: int, season_year: int, swid: str,
                espn_s2: str) -> "EspnClient":
        from espn_api.football import League

        try:
            league = League(league_id=league_id, year=season_year,
                             espn_s2=espn_s2, swid=swid)
        except Exception as exc:
            raise EspnAuthError(
                f"Could not authenticate with ESPN ({type(exc).__name__}). "
                "Your session cookies may have expired or been mistyped — "
                "restart the app to be prompted for fresh SWID/espn_s2 "
                "values. If this keeps happening, also double-check your "
                "league ID, season year, and network connection."
            ) from exc
        return cls(league)

    def get_teams(self) -> list[EspnTeam]:
        return [
            EspnTeam(
                id=t.team_id,
                name=t.team_name,
                wins=t.wins,
                losses=t.losses,
                ties=getattr(t, "ties", 0),
                points_for=t.points_for,
                points_against=t.points_against,
            )
            for t in self._league.teams
        ]

    def get_rosters(self) -> dict[int, list[EspnPlayer]]:
        return {
            t.team_id: [_map_player(p, t.team_id) for p in t.roster]
            for t in self._league.teams
        }

    def get_free_agents(self, size: int = 100) -> list[EspnPlayer]:
        return [_map_player(p, None) for p in self._league.free_agents(size=size)]

    @property
    def current_week(self) -> int:
        return self._league.current_week
