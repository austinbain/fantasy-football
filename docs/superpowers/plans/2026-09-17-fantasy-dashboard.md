# ESPN Fantasy Football Insights Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally-run FastAPI dashboard that pulls a private ESPN Fantasy Football league (plus free nflverse stats) into a SQLite cache and surfaces trade analysis, waiver rankings, lineup recommendations, and league analytics.

**Architecture:** Single Python process. `espn_client.py` and `stats_client.py` wrap third-party data sources behind small dataclass-based interfaces. `sync.py` normalizes both into SQLite (via SQLAlchemy models). Pure-logic analytics modules (`projections`, `trade_analyzer`, `waiver`, `lineup`, `power_rankings`) read only from the DB, so they're unit-testable without any network access. FastAPI routes + Jinja2/HTMX templates render the analytics as an interactive local dashboard.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, SQLAlchemy + SQLite, Jinja2, HTMX (CDN script, no build step), `espn_api`, `nfl_data_py`, pandas, pytest, pytest-mock.

**Spec:** [docs/superpowers/specs/2026-09-17-fantasy-dashboard-design.md](../specs/2026-09-17-fantasy-dashboard-design.md)

## Global Constraints

- Python 3.11+.
- No live network calls in unit tests — `espn_api` and `nfl_data_py` are always mocked/injected in tests; only manual runs against the real dashboard exercise the live APIs (per spec's Testing section).
- `.env` holds only non-sensitive config — `ESPN_LEAGUE_ID`, `ESPN_SEASON_YEAR`, `MY_TEAM_ID`, optional `DB_PATH` — and is gitignored regardless. ESPN session cookies (`SWID`, `espn_s2`) are never written to `.env` or any file: `run.py` prompts for them interactively on every launch (falling back to `ESPN_SWID`/`ESPN_S2` shell environment variables if the user set those for the session), with printed instructions on how to find them, and holds them in memory only for that process's lifetime.
- No background scheduler — data refresh is a manual, explicit action (a "Refresh Data" button), per spec's Data Flow section.
- Projection math must stay inspectable (simple weighted formula), not a black-box model, per spec's `projections.py` section.

---

## Task 1: Project Scaffolding & Configuration

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`
- Create: `README.md`

**Interfaces:**
- Produces: `Config` dataclass with fields `league_id: int`, `season_year: int`, `my_team_id: int`, `db_path: str` (no cookie fields — cookies are never persisted); `ConfigError(Exception)`; `load_config(env_path: str = ".env") -> Config`; `COOKIE_INSTRUCTIONS: str`; `get_espn_credentials(input_fn=input, secret_input_fn=None) -> tuple[str, str]` (prompts interactively for `SWID`/`espn_s2`, falling back to `ESPN_SWID`/`ESPN_S2` env vars if already set — never reads them from a file).

- [ ] **Step 1: Create scaffolding files**

`requirements.txt`:
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
jinja2==3.1.4
python-multipart==0.0.9
python-dotenv==1.0.1
sqlalchemy==2.0.35
espn_api==0.44.0
nfl_data_py==0.3.3
pandas==2.2.3
pytest==8.3.3
pytest-mock==3.14.0
httpx==0.27.2
```

`.env.example`:
```
ESPN_LEAGUE_ID=123456
ESPN_SEASON_YEAR=2026
MY_TEAM_ID=1
DB_PATH=fantasy.db
```

Note: ESPN session cookies (`SWID`, `espn_s2`) intentionally do NOT go
here. They're requested interactively when you run `python run.py` and
are never written to disk — see the Setup section below.

`.gitignore`:
```
.env
*.db
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
```

`README.md`:
```markdown
# Fantasy Football Insights Dashboard

Local dashboard for a private ESPN Fantasy Football league: trade
analysis, waiver rankings, lineup recommendations, league analytics.

## Setup

1. `python -m venv .venv && .venv\Scripts\activate` (Windows) or
   `source .venv/bin/activate` (macOS/Linux)
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in `ESPN_LEAGUE_ID`,
   `ESPN_SEASON_YEAR`, and `MY_TEAM_ID` (from your league's ESPN URL
   and team page). Do **not** put ESPN cookies in this file.
4. `python run.py` — starts the server, prompts you for your ESPN
   `SWID` and `espn_s2` session cookies (printing instructions on
   where to find them in your browser), then opens your browser.
   These cookies are held in memory only for this run and are never
   written to `.env` or any other file.

   To skip retyping them every run, you can instead export them as
   shell environment variables for your terminal session (still never
   committed to a file):
   ```powershell
   $env:ESPN_SWID = "{...}"; $env:ESPN_S2 = "..."
   ```
```

- [ ] **Step 2: Create a virtual environment and install dependencies**

```bash
python -m venv .venv
# Windows:
.venv/Scripts/pip install -r requirements.txt
# macOS/Linux:
.venv/bin/pip install -r requirements.txt
```

Every later task in this plan runs `pytest` assuming this environment is
active. On Windows, activate it per-session with
`.venv\Scripts\Activate.ps1` (PowerShell) or `.venv/Scripts/activate`
(Git Bash) before running `pytest`/`python run.py`; on macOS/Linux use
`source .venv/bin/activate`. `.venv/` is already covered by the
`.gitignore` from Step 1.

- [ ] **Step 3: Write failing tests for config loading**

```python
# tests/test_config.py
import pytest
from app.config import load_config, get_espn_credentials, ConfigError


def write_env(tmp_path, **overrides):
    values = {
        "ESPN_LEAGUE_ID": "123456",
        "ESPN_SEASON_YEAR": "2026",
        "MY_TEAM_ID": "1",
    }
    values.update(overrides)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(f"{k}={v}" for k, v in values.items() if v is not None)
    )
    return env_path


def test_load_config_success(tmp_path):
    env_path = write_env(tmp_path)
    config = load_config(str(env_path))
    assert config.league_id == 123456
    assert config.season_year == 2026
    assert config.my_team_id == 1
    assert config.db_path == "fantasy.db"


def test_load_config_missing_required_var_raises(tmp_path):
    env_path = write_env(tmp_path, MY_TEAM_ID=None)
    with pytest.raises(ConfigError, match="MY_TEAM_ID"):
        load_config(str(env_path))


def test_load_config_never_reads_espn_cookies_from_file(tmp_path):
    # Even if a stray .env has cookie values in it (e.g. a leftover from
    # an older setup), Config must not surface them - they must only ever
    # come from get_espn_credentials(), never from load_config().
    env_path = write_env(tmp_path, ESPN_SWID="{SHOULD-BE-IGNORED}")
    config = load_config(str(env_path))
    assert not hasattr(config, "espn_swid")


def test_get_espn_credentials_uses_env_vars_if_present(monkeypatch):
    monkeypatch.setenv("ESPN_SWID", "{ENV-SWID}")
    monkeypatch.setenv("ESPN_S2", "env-s2-value")
    swid, espn_s2 = get_espn_credentials()
    assert swid == "{ENV-SWID}"
    assert espn_s2 == "env-s2-value"


def test_get_espn_credentials_prompts_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("ESPN_SWID", raising=False)
    monkeypatch.delenv("ESPN_S2", raising=False)
    swid, espn_s2 = get_espn_credentials(
        input_fn=lambda _: "{PROMPTED-SWID}",
        secret_input_fn=lambda _: "prompted-s2-value",
    )
    assert swid == "{PROMPTED-SWID}"
    assert espn_s2 == "prompted-s2-value"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 5: Implement config.py**

```python
# app/config.py
import getpass
import os
from dataclasses import dataclass

from dotenv import load_dotenv

REQUIRED_VARS = ["ESPN_LEAGUE_ID", "ESPN_SEASON_YEAR", "MY_TEAM_ID"]

COOKIE_INSTRUCTIONS = """
ESPN cookies are needed to access your private league. They are requested
each time you start the app and are never written to disk.

To find them:
  1. Log into https://www.espn.com and open your fantasy league.
  2. Open browser DevTools (F12) -> Application (Chrome) or Storage
     (Firefox) tab -> Cookies -> https://www.espn.com.
  3. Copy the value of the 'SWID' cookie (looks like {XXXXXXXX-XXXX-...}).
  4. Copy the value of the 'espn_s2' cookie (a long encoded string).

Tip: to skip retyping these every run, set them as shell environment
variables for this terminal session instead (never in a committed file):
  PowerShell:  $env:ESPN_SWID = "{...}"; $env:ESPN_S2 = "..."
""".strip()


class ConfigError(Exception):
    pass


@dataclass
class Config:
    league_id: int
    season_year: int
    my_team_id: int
    db_path: str = "fantasy.db"


def load_config(env_path: str = ".env") -> Config:
    load_dotenv(env_path, override=True)
    missing = [key for key in REQUIRED_VARS if not os.getenv(key)]
    if missing:
        raise ConfigError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    return Config(
        league_id=int(os.environ["ESPN_LEAGUE_ID"]),
        season_year=int(os.environ["ESPN_SEASON_YEAR"]),
        my_team_id=int(os.environ["MY_TEAM_ID"]),
        db_path=os.getenv("DB_PATH", "fantasy.db"),
    )


def get_espn_credentials(input_fn=input, secret_input_fn=None) -> tuple[str, str]:
    """Get ESPN session cookies, prompting interactively rather than ever
    reading them from a file. Falls back to ESPN_SWID/ESPN_S2 shell
    environment variables if the user already set those for convenience."""
    if secret_input_fn is None:
        secret_input_fn = getpass.getpass

    swid = os.getenv("ESPN_SWID")
    espn_s2 = os.getenv("ESPN_S2")
    if swid and espn_s2:
        return swid, espn_s2

    print(COOKIE_INSTRUCTIONS)
    swid = input_fn("SWID cookie value: ").strip()
    espn_s2 = secret_input_fn("espn_s2 cookie value: ").strip()
    return swid, espn_s2
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example .gitignore README.md app/__init__.py app/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: add project scaffolding and interactive ESPN cookie prompt"
```

---

## Task 2: Database Models & Session Management

**Files:**
- Create: `app/models.py`
- Create: `app/db.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: `Base` (SQLAlchemy declarative base); ORM classes `Team`, `Player`, `WeeklyStat`, `DefenseVsPosition`, `Matchup`; `make_engine(db_path: str) -> Engine`; `make_session_factory(engine) -> sessionmaker`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_models.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.db import make_engine, make_session_factory
from app.models import Team, Player, WeeklyStat, DefenseVsPosition


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()
    yield session
    session.close()


def test_create_team_and_player(session):
    team = Team(id=1, name="Dynasty Warriors", wins=5, losses=3, ties=0,
                points_for=650.5, points_against=600.0)
    session.add(team)
    session.commit()

    player = Player(id=100, name="Test Player", position="RB",
                     pro_team="KC", team_id=team.id)
    session.add(player)
    session.commit()

    fetched = session.query(Player).filter_by(id=100).one()
    assert fetched.team.name == "Dynasty Warriors"


def test_free_agent_has_null_team(session):
    player = Player(id=200, name="Free Agent", position="WR", pro_team="MIA")
    session.add(player)
    session.commit()

    fetched = session.query(Player).filter_by(id=200).one()
    assert fetched.team_id is None


def test_weekly_stat_unique_constraint(session):
    player = Player(id=300, name="Stat Player", position="QB", pro_team="BUF")
    session.add(player)
    session.commit()

    session.add(WeeklyStat(player_id=300, week=1, season=2026,
                            fantasy_points=20.5))
    session.commit()

    session.add(WeeklyStat(player_id=300, week=1, season=2026,
                            fantasy_points=99.0))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_defense_vs_position_unique_constraint(session):
    session.add(DefenseVsPosition(pro_team="SF", position="RB", week=1,
                                   season=2026, points_allowed=12.3))
    session.commit()

    session.add(DefenseVsPosition(pro_team="SF", position="RB", week=1,
                                   season=2026, points_allowed=99.0))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: Implement models.py and db.py**

```python
# app/models.py
from sqlalchemy import (Column, Integer, String, Float, ForeignKey,
                         UniqueConstraint)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    ties = Column(Integer, default=0)
    points_for = Column(Float, default=0.0)
    points_against = Column(Float, default=0.0)


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    position = Column(String, nullable=False)
    pro_team = Column(String)
    injury_status = Column(String, default="ACTIVE")
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)
    gsis_id = Column(String, nullable=True)
    espn_projected_points = Column(Float, nullable=True)

    team = relationship("Team", backref="roster")


class WeeklyStat(Base):
    __tablename__ = "weekly_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    fantasy_points = Column(Float, default=0.0)
    espn_projected_points = Column(Float, nullable=True)
    opponent_pro_team = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("player_id", "week", "season",
                          name="uq_player_week_season"),
    )


class DefenseVsPosition(Base):
    __tablename__ = "defense_vs_position"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pro_team = Column(String, nullable=False)
    position = Column(String, nullable=False)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    points_allowed = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("pro_team", "position", "week", "season",
                          name="uq_dvp"),
    )


class Matchup(Base):
    __tablename__ = "matchups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    week = Column(Integer, nullable=False)
    season = Column(Integer, nullable=False)
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    home_score = Column(Float, default=0.0)
    away_score = Column(Float, default=0.0)
```

```python
# app/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base


def make_engine(db_path: str):
    url = "sqlite:///:memory:" if db_path == ":memory:" else f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app/models.py app/db.py tests/test_models.py
git commit -m "feat: add SQLAlchemy models and session factory"
```

---

## Task 3: ESPN Client Wrapper

**Files:**
- Create: `app/espn_client.py`
- Create: `tests/fixtures/espn_fake.py`
- Create: `tests/test_espn_client.py`

**Interfaces:**
- Consumes: `espn_api.football.League` (constructed only in `EspnClient.connect`, never in tests).
- Produces: `EspnPlayer` dataclass (`id`, `name`, `position`, `pro_team`, `injury_status`, `team_id: int | None`, `projected_points`, `actual_points`); `EspnTeam` dataclass (`id`, `name`, `wins`, `losses`, `ties`, `points_for`, `points_against`); `EspnClient` with `EspnClient(league)` constructor, `EspnClient.connect(league_id, season_year, swid, espn_s2) -> EspnClient` classmethod, `.get_teams() -> list[EspnTeam]`, `.get_rosters() -> dict[int, list[EspnPlayer]]` (keyed by team id), `.get_free_agents(size=100) -> list[EspnPlayer]`, `.current_week -> int` property.

- [ ] **Step 1: Write a fake league fixture matching `espn_api`'s shape**

```python
# tests/fixtures/espn_fake.py
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
```

- [ ] **Step 2: Write failing tests for the wrapper**

```python
# tests/test_espn_client.py
from app.espn_client import EspnClient
from tests.fixtures.espn_fake import FakeEspnLeague, FakeEspnTeam, FakeEspnPlayer


def make_fake_league():
    rb = FakeEspnPlayer(101, "Star RB", "RB", "SF",
                         projected_total_points=18.2, total_points=150.0)
    wr = FakeEspnPlayer(102, "Star WR", "WR", "MIA",
                         projected_total_points=14.5, total_points=120.0)
    fa = FakeEspnPlayer(999, "Waiver Guy", "TE", "NYJ",
                         projected_total_points=5.0, total_points=10.0)
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_espn_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.espn_client'`

- [ ] **Step 4: Implement espn_client.py**

```python
# app/espn_client.py
from dataclasses import dataclass


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
    return EspnPlayer(
        id=raw_player.playerId,
        name=raw_player.name,
        position=raw_player.position,
        pro_team=raw_player.proTeam,
        injury_status=getattr(raw_player, "injuryStatus", "ACTIVE"),
        team_id=team_id,
        projected_points=getattr(raw_player, "projected_total_points", 0.0),
        actual_points=getattr(raw_player, "total_points", 0.0),
    )


class EspnClient:
    def __init__(self, league):
        self._league = league

    @classmethod
    def connect(cls, league_id: int, season_year: int, swid: str,
                espn_s2: str) -> "EspnClient":
        from espn_api.football import League

        league = League(league_id=league_id, year=season_year,
                         espn_s2=espn_s2, swid=swid)
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_espn_client.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add app/espn_client.py tests/fixtures/espn_fake.py tests/test_espn_client.py tests/fixtures/__init__.py
git commit -m "feat: add ESPN client wrapper with injectable league dependency"
```

Note: create an empty `tests/fixtures/__init__.py` alongside the fixture file so it's importable as a package.

---

## Task 4: Stats Client Wrapper (nflverse)

**Files:**
- Create: `app/stats_client.py`
- Create: `tests/test_stats_client.py`

**Interfaces:**
- Produces: `StatsClient` with constructor `StatsClient(weekly_data_fn=None, ids_fn=None)` (defaults to the real `nfl_data_py` functions, injectable for tests), `.get_weekly_stats(season_year: int) -> pandas.DataFrame` (columns: `gsis_id`, `player_name`, `position`, `recent_team`, `opponent_team`, `week`, `fantasy_points`), `.get_defense_vs_position(season_year: int) -> pandas.DataFrame` (columns: `pro_team`, `position`, `week`, `points_allowed` — the sum of `fantasy_points` scored by players of that position against that team, per week), `.get_player_id_crosswalk() -> pandas.DataFrame` (columns: `espn_id`, `gsis_id`, `name`).

- [ ] **Step 1: Write failing tests using injected fake data functions**

```python
# tests/test_stats_client.py
import pandas as pd

from app.stats_client import StatsClient


def fake_weekly_data_fn(years):
    return pd.DataFrame([
        {"gsis_id": "g1", "player_name": "Star RB", "position": "RB",
         "recent_team": "SF", "opponent_team": "SEA", "week": 1,
         "fantasy_points": 22.4, "season": 2026},
        {"gsis_id": "g2", "player_name": "Other RB", "position": "RB",
         "recent_team": "LAR", "opponent_team": "SEA", "week": 1,
         "fantasy_points": 10.1, "season": 2026},
        {"gsis_id": "g3", "player_name": "Star WR", "position": "WR",
         "recent_team": "MIA", "opponent_team": "BUF", "week": 1,
         "fantasy_points": 15.0, "season": 2026},
    ])


def fake_ids_fn():
    return pd.DataFrame([
        {"espn_id": "101", "gsis_id": "g1", "name": "Star RB"},
        {"espn_id": "102", "gsis_id": "g3", "name": "Star WR"},
    ])


def test_get_weekly_stats_filters_by_season():
    client = StatsClient(weekly_data_fn=fake_weekly_data_fn, ids_fn=fake_ids_fn)
    df = client.get_weekly_stats(2026)
    assert set(df["player_name"]) == {"Star RB", "Other RB", "Star WR"}
    assert "fantasy_points" in df.columns


def test_get_defense_vs_position_aggregates_points_allowed():
    client = StatsClient(weekly_data_fn=fake_weekly_data_fn, ids_fn=fake_ids_fn)
    dvp = client.get_defense_vs_position(2026)
    seattle_rb_row = dvp[(dvp["pro_team"] == "SEA") & (dvp["position"] == "RB")
                         & (dvp["week"] == 1)].iloc[0]
    assert seattle_rb_row["points_allowed"] == 22.4 + 10.1


def test_get_player_id_crosswalk():
    client = StatsClient(weekly_data_fn=fake_weekly_data_fn, ids_fn=fake_ids_fn)
    crosswalk = client.get_player_id_crosswalk()
    row = crosswalk[crosswalk["espn_id"] == "101"].iloc[0]
    assert row["gsis_id"] == "g1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stats_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.stats_client'`

- [ ] **Step 3: Implement stats_client.py**

```python
# app/stats_client.py
import pandas as pd


class StatsClient:
    def __init__(self, weekly_data_fn=None, ids_fn=None):
        if weekly_data_fn is None:
            import nfl_data_py as nfl
            weekly_data_fn = nfl.import_weekly_data
        if ids_fn is None:
            import nfl_data_py as nfl
            ids_fn = nfl.import_ids
        self._weekly_data_fn = weekly_data_fn
        self._ids_fn = ids_fn

    def get_weekly_stats(self, season_year: int) -> pd.DataFrame:
        df = self._weekly_data_fn([season_year])
        return df[df["season"] == season_year].reset_index(drop=True)

    def get_defense_vs_position(self, season_year: int) -> pd.DataFrame:
        weekly = self.get_weekly_stats(season_year)
        grouped = (
            weekly.groupby(["opponent_team", "position", "week"])["fantasy_points"]
            .sum()
            .reset_index()
            .rename(columns={"opponent_team": "pro_team",
                              "fantasy_points": "points_allowed"})
        )
        return grouped

    def get_player_id_crosswalk(self) -> pd.DataFrame:
        ids = self._ids_fn()
        return ids[["espn_id", "gsis_id", "name"]].dropna(subset=["espn_id"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stats_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/stats_client.py tests/test_stats_client.py
git commit -m "feat: add nflverse stats client with defense-vs-position aggregation"
```

---

## Task 5: Sync Service

**Files:**
- Create: `app/sync.py`
- Create: `tests/test_sync.py`

**Interfaces:**
- Consumes: `EspnClient.get_teams/get_rosters/get_free_agents/current_week` (Task 3), `StatsClient.get_weekly_stats/get_defense_vs_position/get_player_id_crosswalk` (Task 4), `Team`/`Player`/`WeeklyStat`/`DefenseVsPosition` models (Task 2).
- Produces: `SyncResult` dataclass (`teams_synced: int`, `players_synced: int`, `weekly_stats_synced: int`, `unmatched_players: list[str]`); `sync_all(session, espn_client, stats_client, season_year: int) -> SyncResult`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sync.py
import pandas as pd

from app.db import make_engine, make_session_factory
from app.espn_client import EspnClient, EspnTeam, EspnPlayer
from app.models import Player, WeeklyStat, DefenseVsPosition
from app.sync import sync_all


class FakeEspnClient:
    def get_teams(self):
        return [EspnTeam(id=1, name="Dynasty Warriors", wins=5, losses=3,
                          ties=0, points_for=650.5, points_against=600.0)]

    def get_rosters(self):
        return {1: [EspnPlayer(id=101, name="Star RB", position="RB",
                                pro_team="SF", injury_status="ACTIVE",
                                team_id=1, projected_points=18.2,
                                actual_points=150.0)]}

    def get_free_agents(self, size=100):
        return [EspnPlayer(id=999, name="Waiver Guy", position="TE",
                            pro_team="NYJ", injury_status="ACTIVE",
                            team_id=None, projected_points=5.0,
                            actual_points=10.0)]

    @property
    def current_week(self):
        return 2


class FakeStatsClient:
    def get_weekly_stats(self, season_year):
        return pd.DataFrame([
            {"gsis_id": "g1", "player_name": "Star RB", "position": "RB",
             "recent_team": "SF", "opponent_team": "SEA", "week": 1,
             "fantasy_points": 22.4},
        ])

    def get_defense_vs_position(self, season_year):
        return pd.DataFrame([
            {"pro_team": "SEA", "position": "RB", "week": 1,
             "points_allowed": 22.4},
        ])

    def get_player_id_crosswalk(self):
        return pd.DataFrame([
            {"espn_id": "101", "gsis_id": "g1", "name": "Star RB"},
        ])


def make_session():
    engine = make_engine(":memory:")
    return make_session_factory(engine)()


def test_sync_all_creates_teams_players_and_stats():
    session = make_session()
    result = sync_all(session, FakeEspnClient(), FakeStatsClient(), 2026)

    assert result.teams_synced == 1
    assert result.players_synced == 2
    assert result.weekly_stats_synced == 1

    rb = session.query(Player).filter_by(id=101).one()
    assert rb.gsis_id == "g1"
    assert rb.team_id == 1
    assert rb.espn_projected_points == 18.2

    fa = session.query(Player).filter_by(id=999).one()
    assert fa.team_id is None

    stat = session.query(WeeklyStat).filter_by(player_id=101).one()
    assert stat.fantasy_points == 22.4

    dvp = session.query(DefenseVsPosition).filter_by(pro_team="SEA").one()
    assert dvp.points_allowed == 22.4


def test_sync_all_reports_unmatched_players():
    session = make_session()
    result = sync_all(session, FakeEspnClient(), FakeStatsClient(), 2026)
    assert "Waiver Guy" in result.unmatched_players


def test_sync_all_is_idempotent():
    session = make_session()
    sync_all(session, FakeEspnClient(), FakeStatsClient(), 2026)
    result = sync_all(session, FakeEspnClient(), FakeStatsClient(), 2026)
    assert result.teams_synced == 1
    assert session.query(Player).count() == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sync'`

- [ ] **Step 3: Implement sync.py**

```python
# app/sync.py
from dataclasses import dataclass, field

from app.models import Team, Player, WeeklyStat, DefenseVsPosition


@dataclass
class SyncResult:
    teams_synced: int = 0
    players_synced: int = 0
    weekly_stats_synced: int = 0
    unmatched_players: list = field(default_factory=list)


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

    for espn_team in espn_client.get_teams():
        _upsert_team(session, espn_team)
        result.teams_synced += 1
    session.commit()

    crosswalk = stats_client.get_player_id_crosswalk()
    gsis_by_espn_id = dict(zip(crosswalk["espn_id"], crosswalk["gsis_id"]))
    gsis_by_name = dict(zip(crosswalk["name"], crosswalk["gsis_id"]))

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

    gsis_to_espn_id = {v: k for k, v in gsis_by_espn_id.items()}
    weekly = stats_client.get_weekly_stats(season_year)
    for _, row in weekly.iterrows():
        espn_id = gsis_to_espn_id.get(row["gsis_id"])
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
        existing.fantasy_points = float(row["fantasy_points"])
        existing.opponent_pro_team = row.get("opponent_team")
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
        existing.points_allowed = float(row["points_allowed"])
    session.commit()

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/sync.py tests/test_sync.py
git commit -m "feat: add sync service to merge ESPN and nflverse data into SQLite"
```

---

## Task 6: Projections Engine

**Files:**
- Create: `app/projections.py`
- Create: `tests/test_projections.py`

**Interfaces:**
- Consumes: `Player` (including `espn_projected_points`, used as a fallback when no nflverse-sourced `WeeklyStat` rows exist for the player — the spec's "nflverse data unavailable" case), `WeeklyStat`, `DefenseVsPosition` models (Task 2).
- Produces: `Projection` dataclass (`player_id: int`, `points: float`, `season_avg: float`, `recent_form: float`, `matchup_multiplier: float`); `project_player(session, player_id: int, season_year: int, upcoming_week: int, upcoming_opponent: str) -> Projection`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_projections.py
import pytest

from app.db import make_engine, make_session_factory
from app.models import Player, WeeklyStat, DefenseVsPosition
from app.projections import project_player


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()
    session.add(Player(id=1, name="Star RB", position="RB", pro_team="SF"))
    for week, points in [(1, 10.0), (2, 20.0), (3, 30.0)]:
        session.add(WeeklyStat(player_id=1, week=week, season=2026,
                                fantasy_points=points))
    # League-average points allowed to RBs is 15; SEA allows 30 (tough matchup for offense = allows more, i.e. weak defense)
    session.add(DefenseVsPosition(pro_team="SEA", position="RB", week=4,
                                   season=2026, points_allowed=30.0))
    session.add(DefenseVsPosition(pro_team="LAR", position="RB", week=4,
                                   season=2026, points_allowed=10.0))
    session.commit()
    yield session
    session.close()


def test_project_player_blends_season_avg_and_recent_form(session):
    projection = project_player(session, player_id=1, season_year=2026,
                                 upcoming_week=4, upcoming_opponent="LAR")
    assert projection.season_avg == pytest.approx(20.0)
    # last-3-week average with weight toward recency: (10*1 + 20*2 + 30*3) / 6 = 21.67
    assert projection.recent_form == pytest.approx(21.6667, rel=1e-3)


def test_project_player_favorable_matchup_increases_points(session):
    easy_matchup = project_player(session, player_id=1, season_year=2026,
                                   upcoming_week=4, upcoming_opponent="SEA")
    tough_matchup = project_player(session, player_id=1, season_year=2026,
                                    upcoming_week=4, upcoming_opponent="LAR")
    assert easy_matchup.points > tough_matchup.points


def test_project_player_no_defense_data_defaults_to_neutral_matchup(session):
    projection = project_player(session, player_id=1, season_year=2026,
                                 upcoming_week=4, upcoming_opponent="UNKNOWN")
    assert projection.matchup_multiplier == pytest.approx(1.0)


def test_project_player_falls_back_to_espn_projection_when_no_nflverse_stats(session):
    session.add(Player(id=2, name="No Stats Player", position="WR",
                        pro_team="DAL", espn_projected_points=12.5))
    session.commit()

    projection = project_player(session, player_id=2, season_year=2026,
                                 upcoming_week=4, upcoming_opponent="LAR")
    assert projection.points == pytest.approx(12.5)
    assert projection.matchup_multiplier == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_projections.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.projections'`

- [ ] **Step 3: Implement projections.py**

```python
# app/projections.py
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
        .filter(DefenseVsPosition.week < upcoming_week)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_projections.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/projections.py tests/test_projections.py
git commit -m "feat: add transparent player projection engine"
```

---

## Task 7: Trade Analyzer

**Files:**
- Create: `app/analytics/__init__.py`
- Create: `app/analytics/trade_analyzer.py`
- Create: `tests/test_trade_analyzer.py`

**Interfaces:**
- Consumes: `project_player` (Task 6), `Player`, `Team` models (Task 2).
- Produces: `TradeSide` dataclass (`team_id: int`, `player_ids: list[int]`); `TradeEvaluation` dataclass (`side_a_value: float`, `side_b_value: float`, `difference_pct: float`, `is_lopsided: bool`); `TradeSuggestion` dataclass (`give_player_id: int`, `get_player_id: int`, `other_team_id: int`, `rationale: str`); `evaluate_trade(session, side_a: TradeSide, side_b: TradeSide, season_year: int, week: int, threshold_pct: float = 0.2) -> TradeEvaluation`; `suggest_trades(session, my_team_id: int, season_year: int, week: int, max_suggestions: int = 5) -> list[TradeSuggestion]`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_trade_analyzer.py
import pytest

from app.db import make_engine, make_session_factory
from app.models import Player, Team, WeeklyStat
from app.analytics.trade_analyzer import TradeSide, evaluate_trade, suggest_trades


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()

    session.add_all([
        Team(id=1, name="My Team"),
        Team(id=2, name="Rival Team"),
    ])
    session.add_all([
        Player(id=1, name="Great RB", position="RB", pro_team="SF", team_id=1),
        Player(id=2, name="Backup RB", position="RB", pro_team="SF", team_id=1),
        Player(id=3, name="Great WR", position="WR", pro_team="MIA", team_id=2),
        Player(id=4, name="Backup WR", position="WR", pro_team="MIA", team_id=2),
    ])
    stats = {1: 25.0, 2: 8.0, 3: 24.0, 4: 6.0}
    for player_id, points in stats.items():
        for week in range(1, 4):
            session.add(WeeklyStat(player_id=player_id, week=week, season=2026,
                                    fantasy_points=points))
    session.commit()
    yield session
    session.close()


def test_evaluate_trade_balanced_is_not_lopsided(session):
    side_a = TradeSide(team_id=1, player_ids=[1])
    side_b = TradeSide(team_id=2, player_ids=[3])
    result = evaluate_trade(session, side_a, side_b, season_year=2026, week=4)
    assert result.is_lopsided is False
    assert result.side_a_value == pytest.approx(result.side_b_value, rel=0.05)


def test_evaluate_trade_lopsided_flags_it(session):
    side_a = TradeSide(team_id=1, player_ids=[1])
    side_b = TradeSide(team_id=2, player_ids=[4])
    result = evaluate_trade(session, side_a, side_b, season_year=2026, week=4)
    assert result.is_lopsided is True
    assert result.side_a_value > result.side_b_value


def test_suggest_trades_pairs_surplus_with_need(session):
    suggestions = suggest_trades(session, my_team_id=1, season_year=2026, week=4)
    assert isinstance(suggestions, list)
    for suggestion in suggestions:
        assert suggestion.other_team_id == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_trade_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analytics'`

- [ ] **Step 3: Implement trade_analyzer.py**

```python
# app/analytics/trade_analyzer.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_trade_analyzer.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/analytics/__init__.py app/analytics/trade_analyzer.py tests/test_trade_analyzer.py
git commit -m "feat: add trade valuation and trade suggestion engine"
```

---

## Task 8: Waiver Wire Ranker

**Files:**
- Create: `app/analytics/waiver.py`
- Create: `tests/test_waiver.py`

**Interfaces:**
- Consumes: `project_player` (Task 6), `Player` model (Task 2).
- Produces: `WaiverCandidate` dataclass (`player_id: int`, `name: str`, `position: str`, `projected_points: float`, `need_score: float`, `combined_score: float`); `rank_waiver_wire(session, team_id: int, season_year: int, week: int, limit: int = 25) -> list[WaiverCandidate]`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_waiver.py
import pytest

from app.db import make_engine, make_session_factory
from app.models import Player, WeeklyStat
from app.analytics.waiver import rank_waiver_wire


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()

    # My team has two RBs (adequate depth) and zero WRs (a need).
    session.add_all([
        Player(id=1, name="My RB1", position="RB", pro_team="SF", team_id=1),
        Player(id=2, name="My RB2", position="RB", pro_team="KC", team_id=1),
    ])
    # Free agents: one RB, one WR, similar raw projections.
    session.add_all([
        Player(id=10, name="FA RB", position="RB", pro_team="NYJ"),
        Player(id=11, name="FA WR", position="WR", pro_team="DAL"),
    ])
    for player_id in [1, 2, 10, 11]:
        for week in range(1, 4):
            session.add(WeeklyStat(player_id=player_id, week=week, season=2026,
                                    fantasy_points=12.0))
    session.commit()
    yield session
    session.close()


def test_rank_waiver_wire_prioritizes_need_position(session):
    ranked = rank_waiver_wire(session, team_id=1, season_year=2026, week=4)
    assert ranked[0].position == "WR"
    assert ranked[0].name == "FA WR"


def test_rank_waiver_wire_only_includes_free_agents(session):
    ranked = rank_waiver_wire(session, team_id=1, season_year=2026, week=4)
    ids = {c.player_id for c in ranked}
    assert ids == {10, 11}


def test_rank_waiver_wire_respects_limit(session):
    ranked = rank_waiver_wire(session, team_id=1, season_year=2026, week=4,
                               limit=1)
    assert len(ranked) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_waiver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analytics.waiver'`

- [ ] **Step 3: Implement waiver.py**

```python
# app/analytics/waiver.py
from dataclasses import dataclass

from app.models import Player
from app.projections import project_player

ROSTER_NEED_TARGET = {"QB": 2, "RB": 4, "WR": 4, "TE": 2, "K": 1, "DST": 1}


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_waiver.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/analytics/waiver.py tests/test_waiver.py
git commit -m "feat: add waiver wire ranking by projection and roster need"
```

---

## Task 9: Lineup Optimizer

**Files:**
- Create: `app/analytics/lineup.py`
- Create: `tests/test_lineup.py`

**Interfaces:**
- Consumes: `project_player` (Task 6), `Player` model (Task 2).
- Produces: `LineupRecommendation` dataclass (`slot: str`, `player_id: int`, `player_name: str`, `projected_points: float`); `STANDARD_SLOTS: list[str]` constant (`["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DST", "K"]`); `recommend_lineup(session, team_id: int, season_year: int, week: int) -> list[LineupRecommendation]`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lineup.py
import pytest

from app.db import make_engine, make_session_factory
from app.models import Player, WeeklyStat
from app.analytics.lineup import recommend_lineup


@pytest.fixture
def session():
    engine = make_engine(":memory:")
    Session = make_session_factory(engine)
    session = Session()

    session.add_all([
        Player(id=1, name="QB1", position="QB", pro_team="KC", team_id=1),
        Player(id=2, name="RB1", position="RB", pro_team="SF", team_id=1),
        Player(id=3, name="RB2", position="RB", pro_team="MIA", team_id=1),
        Player(id=4, name="RB3 (bench)", position="RB", pro_team="DAL", team_id=1),
        Player(id=5, name="WR1", position="WR", pro_team="BUF", team_id=1),
        Player(id=6, name="WR2", position="WR", pro_team="CIN", team_id=1),
        Player(id=7, name="TE1", position="TE", pro_team="NYJ", team_id=1),
        Player(id=8, name="DST1", position="DST", pro_team="SEA", team_id=1),
        Player(id=9, name="K1", position="K", pro_team="LAR", team_id=1),
    ])
    points = {1: 20, 2: 15, 3: 14, 4: 25, 5: 10, 6: 9, 7: 8, 8: 7, 9: 6}
    for player_id, pts in points.items():
        for week in range(1, 4):
            session.add(WeeklyStat(player_id=player_id, week=week, season=2026,
                                    fantasy_points=pts))
    session.commit()
    yield session
    session.close()


def test_recommend_lineup_fills_all_slots(session):
    lineup = recommend_lineup(session, team_id=1, season_year=2026, week=4)
    slots = [rec.slot for rec in lineup]
    assert slots == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DST", "K"]


def test_recommend_lineup_flex_takes_best_remaining_rb_wr_te(session):
    lineup = recommend_lineup(session, team_id=1, season_year=2026, week=4)
    flex = next(rec for rec in lineup if rec.slot == "FLEX")
    assert flex.player_name == "RB3 (bench)"


def test_recommend_lineup_no_player_used_twice(session):
    lineup = recommend_lineup(session, team_id=1, season_year=2026, week=4)
    player_ids = [rec.player_id for rec in lineup]
    assert len(player_ids) == len(set(player_ids))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_lineup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analytics.lineup'`

- [ ] **Step 3: Implement lineup.py**

```python
# app/analytics/lineup.py
from dataclasses import dataclass

from app.models import Player
from app.projections import project_player

STANDARD_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DST", "K"]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_lineup.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/analytics/lineup.py tests/test_lineup.py
git commit -m "feat: add weekly lineup optimizer"
```

---

## Task 10: Power Rankings & League Analytics

**Files:**
- Create: `app/analytics/power_rankings.py`
- Create: `tests/test_power_rankings.py`

**Interfaces:**
- Consumes: `Team`, `Matchup` models (Task 2).
- Produces: `TeamPowerRanking` dataclass (`team_id: int`, `team_name: str`, `power_score: float`, `rank: int`, `luck_index: float`, `strength_of_schedule: float`); `compute_power_rankings(session, season_year: int) -> list[TeamPowerRanking]`; `StandingsProjection` dataclass (`team_id: int`, `team_name: str`, `projected_wins: float`, `projected_losses: float`); `project_standings(session, season_year: int, remaining_weeks: int, simulations: int = 1000, random_seed: int | None = None) -> list[StandingsProjection]`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_power_rankings.py
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
    projections = project_standings(session, season_year=2026,
                                     remaining_weeks=3, simulations=200,
                                     random_seed=42)
    assert {p.team_id for p in projections} == {1, 2}
    for p in projections:
        assert p.projected_wins + p.projected_losses == pytest.approx(
            (p.projected_wins + p.projected_losses), rel=0  # sanity: no NaN
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_power_rankings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.analytics.power_rankings'`

- [ ] **Step 3: Implement power_rankings.py**

```python
# app/analytics/power_rankings.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_power_rankings.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/analytics/power_rankings.py tests/test_power_rankings.py
git commit -m "feat: add power rankings, luck index, and standings projection"
```

---

## Task 11: FastAPI App Skeleton + Dashboard Page

**Files:**
- Create: `app/web/__init__.py`
- Create: `app/web/app.py`
- Create: `app/web/routes/__init__.py`
- Create: `app/web/routes/dashboard.py`
- Create: `app/web/templates/base.html`
- Create: `app/web/templates/dashboard.html`
- Create: `app/web/templates/partials/sync_status.html`
- Create: `app/web/static/style.css`
- Create: `run.py`
- Create: `tests/test_web_dashboard.py`

**Interfaces:**
- Consumes: `load_config`, `get_espn_credentials` (Task 1), `make_engine`/`make_session_factory` (Task 2), `EspnClient.connect` (Task 3), `StatsClient` (Task 4), `sync_all` (Task 5).
- Produces: `create_app(session_factory, espn_client_factory, stats_client_factory, season_year, my_team_id) -> FastAPI`; module-level `app` in `app/web/app.py` built from real config for `run.py`/uvicorn to import; dependency `get_session` (FastAPI dependency yielding a session bound to the app's session factory) importable by later route tasks via `request.app.state.session_factory`.

- [ ] **Step 1: Write failing tests using FastAPI's TestClient**

```python
# tests/test_web_dashboard.py
import pytest
from fastapi.testclient import TestClient

from app.db import make_engine, make_session_factory
from app.models import Team
from app.web.app import create_app


class FakeEspnClient:
    def get_teams(self):
        return []

    def get_rosters(self):
        return {}

    def get_free_agents(self, size=100):
        return []

    @property
    def current_week(self):
        return 1


class FakeStatsClient:
    def get_weekly_stats(self, season_year):
        import pandas as pd
        return pd.DataFrame(columns=["gsis_id", "player_name", "position",
                                      "recent_team", "opponent_team", "week",
                                      "fantasy_points"])

    def get_defense_vs_position(self, season_year):
        import pandas as pd
        return pd.DataFrame(columns=["pro_team", "position", "week",
                                      "points_allowed"])

    def get_player_id_crosswalk(self):
        import pandas as pd
        return pd.DataFrame(columns=["espn_id", "gsis_id", "name"])


@pytest.fixture
def client():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    session = session_factory()
    session.add(Team(id=1, name="My Team", wins=1, losses=0, points_for=100.0,
                      points_against=80.0))
    session.commit()
    session.close()

    app = create_app(
        session_factory=session_factory,
        espn_client_factory=lambda: FakeEspnClient(),
        stats_client_factory=lambda: FakeStatsClient(),
        season_year=2026,
        my_team_id=1,
    )
    return TestClient(app)


def test_dashboard_page_loads_and_lists_teams(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "My Team" in response.text


def test_refresh_triggers_sync_and_returns_partial(client):
    response = client.post("/sync")
    assert response.status_code == 200
    assert "Synced" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_dashboard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.web'`

- [ ] **Step 3: Implement the app skeleton, dashboard route, templates, and run.py**

```python
# app/web/app.py
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def create_app(session_factory, espn_client_factory, stats_client_factory,
               season_year: int, my_team_id: int) -> FastAPI:
    app = FastAPI()
    app.state.session_factory = session_factory
    app.state.espn_client_factory = espn_client_factory
    app.state.stats_client_factory = stats_client_factory
    app.state.season_year = season_year
    app.state.my_team_id = my_team_id
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")),
               name="static")

    from app.web.routes.dashboard import router as dashboard_router
    app.include_router(dashboard_router)

    return app


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
```

```python
# app/web/routes/dashboard.py
from fastapi import APIRouter, Depends, Request

from app.models import Team
from app.sync import sync_all
from app.web.app import get_session

router = APIRouter()


@router.get("/")
def dashboard(request: Request, session=Depends(get_session)):
    teams = session.query(Team).order_by(Team.wins.desc()).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "dashboard.html",
                                       {"teams": teams})


@router.post("/sync")
def refresh(request: Request, session=Depends(get_session)):
    espn_client = request.app.state.espn_client_factory()
    stats_client = request.app.state.stats_client_factory()
    result = sync_all(session, espn_client, stats_client,
                       request.app.state.season_year)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "partials/sync_status.html",
                                       {"result": result})
```

```html
<!-- app/web/templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Fantasy Dashboard</title>
    <script src="https://unpkg.com/htmx.org@1.9.12/dist/htmx.min.js"
            integrity="sha384-ujb1lZYygJmzgSwoxRggbCHcjc0rB2XoQrxeTUQyRjrOnlCoYta87iKBWq3EsdM2"
            crossorigin="anonymous"></script>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <nav>
        <a href="/">Dashboard</a>
        <a href="/trades">Trade Analyzer</a>
        <a href="/waiver">Waiver Wire</a>
        <a href="/lineup">Lineup</a>
        <a href="/analytics">Analytics</a>
    </nav>
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

```html
<!-- app/web/templates/dashboard.html -->
{% extends "base.html" %}
{% block content %}
<h1>League Dashboard</h1>
<button hx-post="/sync" hx-target="#sync-status" hx-swap="innerHTML">
    Refresh Data
</button>
<div id="sync-status"></div>

<table>
    <thead>
        <tr><th>Team</th><th>Record</th><th>Points For</th></tr>
    </thead>
    <tbody>
        {% for team in teams %}
        <tr>
            <td>{{ team.name }}</td>
            <td>{{ team.wins }}-{{ team.losses }}</td>
            <td>{{ "%.1f"|format(team.points_for) }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

```html
<!-- app/web/templates/partials/sync_status.html -->
<p>
    Synced {{ result.teams_synced }} teams, {{ result.players_synced }}
    players, {{ result.weekly_stats_synced }} weekly stat rows.
    {% if result.unmatched_players %}
    <br>Unmatched players: {{ result.unmatched_players | join(", ") }}
    {% endif %}
</p>
```

```css
/* app/web/static/style.css */
body { font-family: sans-serif; max-width: 960px; margin: 2rem auto; }
nav a { margin-right: 1rem; }
table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
th, td { border: 1px solid #ccc; padding: 0.5rem; text-align: left; }
```

```python
# run.py
import threading
import webbrowser

import uvicorn

from app.config import get_espn_credentials, load_config
from app.db import make_engine, make_session_factory
from app.espn_client import EspnClient
from app.stats_client import StatsClient
from app.web.app import create_app


def main():
    config = load_config()
    swid, espn_s2 = get_espn_credentials()
    engine = make_engine(config.db_path)
    session_factory = make_session_factory(engine)

    def espn_client_factory():
        return EspnClient.connect(config.league_id, config.season_year,
                                   swid, espn_s2)

    app = create_app(
        session_factory=session_factory,
        espn_client_factory=espn_client_factory,
        stats_client_factory=StatsClient,
        season_year=config.season_year,
        my_team_id=config.my_team_id,
    )

    port = 8000
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_dashboard.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/web run.py tests/test_web_dashboard.py
git commit -m "feat: add FastAPI app skeleton and dashboard page"
```

---

## Task 12: Trade Analyzer Page

**Files:**
- Create: `app/web/routes/trades.py`
- Create: `app/web/templates/trades.html`
- Create: `app/web/templates/partials/trade_result.html`
- Create: `tests/test_web_trades.py`
- Modify: `app/web/app.py:create_app` — register the new router (add `from app.web.routes.trades import router as trades_router` and `app.include_router(trades_router)`).
- Modify: `app/web/templates/base.html` — no change needed, nav link already present.

**Interfaces:**
- Consumes: `evaluate_trade`, `TradeSide`, `suggest_trades` (Task 7), `Team`/`Player` models (Task 2), `get_session` (Task 11).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_web_trades.py
import pytest
from fastapi.testclient import TestClient

from app.db import make_engine, make_session_factory
from app.models import Team, Player, WeeklyStat
from app.web.app import create_app


@pytest.fixture
def client():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    session = session_factory()
    session.add_all([
        Team(id=1, name="My Team"),
        Team(id=2, name="Rival Team"),
        Player(id=1, name="Great RB", position="RB", pro_team="SF", team_id=1),
        Player(id=2, name="Great WR", position="WR", pro_team="MIA", team_id=2),
    ])
    for player_id, points in {1: 25.0, 2: 24.0}.items():
        for week in range(1, 4):
            session.add(WeeklyStat(player_id=player_id, week=week, season=2026,
                                    fantasy_points=points))
    session.commit()
    session.close()

    app = create_app(
        session_factory=session_factory,
        espn_client_factory=lambda: None,
        stats_client_factory=lambda: None,
        season_year=2026,
        my_team_id=1,
    )
    return TestClient(app)


def test_trades_page_loads_with_team_rosters(client):
    response = client.get("/trades")
    assert response.status_code == 200
    assert "Great RB" in response.text
    assert "Great WR" in response.text


def test_evaluate_trade_endpoint_returns_result_partial(client):
    response = client.post("/trades/evaluate", data={
        "side_a_players": ["1"],
        "side_b_players": ["2"],
        "week": "4",
    })
    assert response.status_code == 200
    assert "Great RB" in response.text or "value" in response.text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_trades.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.web.routes.trades'`

- [ ] **Step 3: Implement trades.py, templates, and register the router**

```python
# app/web/routes/trades.py
from fastapi import APIRouter, Depends, Form, Request

from app.models import Player, Team
from app.analytics.trade_analyzer import TradeSide, evaluate_trade, suggest_trades
from app.web.app import get_session

router = APIRouter()


@router.get("/trades")
def trades_page(request: Request, session=Depends(get_session)):
    teams = session.query(Team).all()
    rosters = {
        team.id: session.query(Player).filter_by(team_id=team.id).all()
        for team in teams
    }
    my_team_id = request.app.state.my_team_id
    suggestions = suggest_trades(session, my_team_id,
                                  request.app.state.season_year, week=1)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "trades.html", {
        "teams": teams, "rosters": rosters, "suggestions": suggestions,
    })


@router.post("/trades/evaluate")
def evaluate_trade_route(
    request: Request,
    side_a_players: list[str] = Form(...),
    side_b_players: list[str] = Form(...),
    week: int = Form(...),
    session=Depends(get_session),
):
    side_a = TradeSide(team_id=0, player_ids=[int(p) for p in side_a_players])
    side_b = TradeSide(team_id=0, player_ids=[int(p) for p in side_b_players])
    result = evaluate_trade(session, side_a, side_b,
                             request.app.state.season_year, week)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "partials/trade_result.html",
                                       {"result": result})
```

```html
<!-- app/web/templates/trades.html -->
{% extends "base.html" %}
{% block content %}
<h1>Trade Analyzer</h1>

<form hx-post="/trades/evaluate" hx-target="#trade-result" hx-swap="innerHTML">
    <label>Week: <input type="number" name="week" value="1"></label>
    <h3>Side A</h3>
    {% for team in teams %}
        {% for player in rosters[team.id] %}
        <label>
            <input type="checkbox" name="side_a_players" value="{{ player.id }}">
            {{ player.name }} ({{ team.name }})
        </label><br>
        {% endfor %}
    {% endfor %}
    <h3>Side B</h3>
    {% for team in teams %}
        {% for player in rosters[team.id] %}
        <label>
            <input type="checkbox" name="side_b_players" value="{{ player.id }}">
            {{ player.name }} ({{ team.name }})
        </label><br>
        {% endfor %}
    {% endfor %}
    <button type="submit">Evaluate</button>
</form>
<div id="trade-result"></div>

<h2>Suggested Trades</h2>
<ul>
{% for s in suggestions %}
    <li>{{ s.rationale }}</li>
{% endfor %}
</ul>
{% endblock %}
```

```html
<!-- app/web/templates/partials/trade_result.html -->
<p>
    Side A value: {{ "%.1f"|format(result.side_a_value) }}<br>
    Side B value: {{ "%.1f"|format(result.side_b_value) }}<br>
    Difference: {{ "%.0f"|format(result.difference_pct * 100) }}%<br>
    {% if result.is_lopsided %}
        <strong>This trade looks lopsided.</strong>
    {% else %}
        This trade looks fair.
    {% endif %}
</p>
```

In `app/web/app.py`, add inside `create_app` (after the dashboard router import/include):

```python
    from app.web.routes.trades import router as trades_router
    app.include_router(trades_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_trades.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/web/routes/trades.py app/web/templates/trades.html app/web/templates/partials/trade_result.html app/web/app.py tests/test_web_trades.py
git commit -m "feat: add trade analyzer page"
```

---

## Task 13: Waiver Wire Page

**Files:**
- Create: `app/web/routes/waiver.py`
- Create: `app/web/templates/waiver.html`
- Create: `tests/test_web_waiver.py`
- Modify: `app/web/app.py:create_app` — register the waiver router.

**Interfaces:**
- Consumes: `rank_waiver_wire` (Task 8), `get_session` (Task 11).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_web_waiver.py
import pytest
from fastapi.testclient import TestClient

from app.db import make_engine, make_session_factory
from app.models import Player, WeeklyStat
from app.web.app import create_app


@pytest.fixture
def client():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    session = session_factory()
    session.add(Player(id=1, name="FA Player", position="RB", pro_team="SF"))
    for week in range(1, 4):
        session.add(WeeklyStat(player_id=1, week=week, season=2026,
                                fantasy_points=15.0))
    session.commit()
    session.close()

    app = create_app(
        session_factory=session_factory,
        espn_client_factory=lambda: None,
        stats_client_factory=lambda: None,
        season_year=2026,
        my_team_id=1,
    )
    return TestClient(app)


def test_waiver_page_lists_ranked_free_agents(client):
    response = client.get("/waiver")
    assert response.status_code == 200
    assert "FA Player" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_waiver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.web.routes.waiver'`

- [ ] **Step 3: Implement waiver route, template, and register the router**

```python
# app/web/routes/waiver.py
from fastapi import APIRouter, Depends, Request

from app.analytics.waiver import rank_waiver_wire
from app.web.app import get_session

router = APIRouter()


@router.get("/waiver")
def waiver_page(request: Request, session=Depends(get_session)):
    candidates = rank_waiver_wire(
        session, request.app.state.my_team_id,
        request.app.state.season_year, week=1,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "waiver.html",
                                       {"candidates": candidates})
```

```html
<!-- app/web/templates/waiver.html -->
{% extends "base.html" %}
{% block content %}
<h1>Waiver Wire</h1>
<table>
    <thead>
        <tr><th>Player</th><th>Position</th><th>Projected</th><th>Need Score</th><th>Combined</th></tr>
    </thead>
    <tbody>
        {% for c in candidates %}
        <tr>
            <td>{{ c.name }}</td>
            <td>{{ c.position }}</td>
            <td>{{ "%.1f"|format(c.projected_points) }}</td>
            <td>{{ "%.2f"|format(c.need_score) }}</td>
            <td>{{ "%.1f"|format(c.combined_score) }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

In `app/web/app.py`, add inside `create_app`:

```python
    from app.web.routes.waiver import router as waiver_router
    app.include_router(waiver_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_waiver.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add app/web/routes/waiver.py app/web/templates/waiver.html app/web/app.py tests/test_web_waiver.py
git commit -m "feat: add waiver wire page"
```

---

## Task 14: Lineup Page

**Files:**
- Create: `app/web/routes/lineup.py`
- Create: `app/web/templates/lineup.html`
- Create: `tests/test_web_lineup.py`
- Modify: `app/web/app.py:create_app` — register the lineup router.

**Interfaces:**
- Consumes: `recommend_lineup` (Task 9), `get_session` (Task 11).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_web_lineup.py
import pytest
from fastapi.testclient import TestClient

from app.db import make_engine, make_session_factory
from app.models import Player, WeeklyStat
from app.web.app import create_app


@pytest.fixture
def client():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    session = session_factory()
    session.add(Player(id=1, name="My QB", position="QB", pro_team="KC",
                        team_id=1))
    for week in range(1, 4):
        session.add(WeeklyStat(player_id=1, week=week, season=2026,
                                fantasy_points=20.0))
    session.commit()
    session.close()

    app = create_app(
        session_factory=session_factory,
        espn_client_factory=lambda: None,
        stats_client_factory=lambda: None,
        season_year=2026,
        my_team_id=1,
    )
    return TestClient(app)


def test_lineup_page_shows_recommended_starters(client):
    response = client.get("/lineup?week=4")
    assert response.status_code == 200
    assert "My QB" in response.text


def test_lineup_page_defaults_week_to_one(client):
    response = client.get("/lineup")
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_lineup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.web.routes.lineup'`

- [ ] **Step 3: Implement lineup route, template, and register the router**

```python
# app/web/routes/lineup.py
from fastapi import APIRouter, Depends, Request

from app.analytics.lineup import recommend_lineup
from app.web.app import get_session

router = APIRouter()


@router.get("/lineup")
def lineup_page(request: Request, week: int = 1, session=Depends(get_session)):
    recommendations = recommend_lineup(
        session, request.app.state.my_team_id,
        request.app.state.season_year, week,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "lineup.html", {
        "recommendations": recommendations, "week": week,
    })
```

```html
<!-- app/web/templates/lineup.html -->
{% extends "base.html" %}
{% block content %}
<h1>Lineup — Week {{ week }}</h1>
<table>
    <thead>
        <tr><th>Slot</th><th>Player</th><th>Projected</th></tr>
    </thead>
    <tbody>
        {% for rec in recommendations %}
        <tr>
            <td>{{ rec.slot }}</td>
            <td>{{ rec.player_name }}</td>
            <td>{{ "%.1f"|format(rec.projected_points) }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

In `app/web/app.py`, add inside `create_app`:

```python
    from app.web.routes.lineup import router as lineup_router
    app.include_router(lineup_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_lineup.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/web/routes/lineup.py app/web/templates/lineup.html app/web/app.py tests/test_web_lineup.py
git commit -m "feat: add weekly lineup page"
```

---

## Task 15: League Analytics Page

**Files:**
- Create: `app/web/routes/analytics.py`
- Create: `app/web/templates/analytics.html`
- Create: `tests/test_web_analytics.py`
- Modify: `app/web/app.py:create_app` — register the analytics router.

**Interfaces:**
- Consumes: `compute_power_rankings`, `project_standings` (Task 10), `get_session` (Task 11).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_web_analytics.py
import pytest
from fastapi.testclient import TestClient

from app.db import make_engine, make_session_factory
from app.models import Team
from app.web.app import create_app


@pytest.fixture
def client():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    session = session_factory()
    session.add_all([
        Team(id=1, name="Team A", wins=5, losses=2, points_for=700.0,
             points_against=650.0),
        Team(id=2, name="Team B", wins=3, losses=4, points_for=650.0,
             points_against=680.0),
    ])
    session.commit()
    session.close()

    app = create_app(
        session_factory=session_factory,
        espn_client_factory=lambda: None,
        stats_client_factory=lambda: None,
        season_year=2026,
        my_team_id=1,
    )
    return TestClient(app)


def test_analytics_page_shows_power_rankings_and_standings(client):
    response = client.get("/analytics")
    assert response.status_code == 200
    assert "Team A" in response.text
    assert "Team B" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_analytics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.web.routes.analytics'`

- [ ] **Step 3: Implement analytics route, template, and register the router**

```python
# app/web/routes/analytics.py
from fastapi import APIRouter, Depends, Request

from app.analytics.power_rankings import compute_power_rankings, project_standings
from app.web.app import get_session

router = APIRouter()


@router.get("/analytics")
def analytics_page(request: Request, session=Depends(get_session)):
    rankings = compute_power_rankings(session, request.app.state.season_year)
    standings = project_standings(session, request.app.state.season_year,
                                   remaining_weeks=3, simulations=500)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "analytics.html", {
        "rankings": rankings, "standings": standings,
    })
```

```html
<!-- app/web/templates/analytics.html -->
{% extends "base.html" %}
{% block content %}
<h1>League Analytics</h1>

<h2>Power Rankings</h2>
<table>
    <thead><tr><th>Rank</th><th>Team</th><th>Score</th><th>Luck</th><th>Strength of Schedule</th></tr></thead>
    <tbody>
        {% for r in rankings %}
        <tr>
            <td>{{ r.rank }}</td>
            <td>{{ r.team_name }}</td>
            <td>{{ "%.2f"|format(r.power_score) }}</td>
            <td>{{ "%.2f"|format(r.luck_index) }}</td>
            <td>{{ "%.3f"|format(r.strength_of_schedule) }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>

<h2>Projected Rest-of-Season Standings</h2>
<table>
    <thead><tr><th>Team</th><th>Projected Wins</th><th>Projected Losses</th></tr></thead>
    <tbody>
        {% for s in standings %}
        <tr>
            <td>{{ s.team_name }}</td>
            <td>{{ "%.1f"|format(s.projected_wins) }}</td>
            <td>{{ "%.1f"|format(s.projected_losses) }}</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

In `app/web/app.py`, add inside `create_app`:

```python
    from app.web.routes.analytics import router as analytics_router
    app.include_router(analytics_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_analytics.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add app/web/routes/analytics.py app/web/templates/analytics.html app/web/app.py tests/test_web_analytics.py
git commit -m "feat: add league analytics page with power rankings and standings projection"
```

---

## Task 16: Error Handling Polish, Unmatched-Players Debug View, and README Finalization

**Files:**
- Modify: `app/espn_client.py` — add `EspnAuthError` and raise it from `EspnClient.connect` on auth failure.
- Modify: `app/web/routes/dashboard.py` — catch `EspnAuthError` in `/sync`, render an error banner partial; add `/debug/unmatched` route.
- Create: `app/web/templates/partials/error_banner.html`
- Create: `app/web/templates/debug_unmatched.html`
- Modify: `tests/test_web_dashboard.py` — add tests for the auth-error banner and the unmatched-players view.
- Modify: `README.md` — add a troubleshooting section for expired cookies.

**Interfaces:**
- Produces: `EspnAuthError(Exception)` in `app/espn_client.py`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_web_dashboard.py`:

```python
from app.espn_client import EspnAuthError


class FailingEspnClient:
    def get_teams(self):
        raise EspnAuthError("ESPN session expired")

    def get_rosters(self):
        return {}

    def get_free_agents(self, size=100):
        return []

    @property
    def current_week(self):
        return 1


def test_sync_with_expired_cookies_shows_error_banner():
    engine = make_engine(":memory:")
    session_factory = make_session_factory(engine)
    app = create_app(
        session_factory=session_factory,
        espn_client_factory=lambda: FailingEspnClient(),
        stats_client_factory=lambda: FakeStatsClient(),
        season_year=2026,
        my_team_id=1,
    )
    test_client = TestClient(app)
    response = test_client.post("/sync")
    assert response.status_code == 200
    assert "session expired" in response.text.lower() or \
           "re-authenticate" in response.text.lower()


def test_debug_unmatched_page_loads(client):
    response = client.get("/debug/unmatched")
    assert response.status_code == 200
```

(The new tests reuse `make_engine`, `make_session_factory`, `create_app`, and `TestClient`, already imported at the top of `tests/test_web_dashboard.py` from Task 11 — add the `EspnAuthError` import alongside the existing imports.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_dashboard.py -v`
Expected: FAIL — `ImportError: cannot import name 'EspnAuthError'` and `404` on `/debug/unmatched`.

- [ ] **Step 3: Implement the error handling and debug view**

In `app/espn_client.py`, add near the top (after imports):

```python
class EspnAuthError(Exception):
    pass
```

And change `EspnClient.connect` to wrap construction:

```python
    @classmethod
    def connect(cls, league_id: int, season_year: int, swid: str,
                espn_s2: str) -> "EspnClient":
        from espn_api.football import League

        try:
            league = League(league_id=league_id, year=season_year,
                             espn_s2=espn_s2, swid=swid)
        except Exception as exc:
            raise EspnAuthError(
                "Could not authenticate with ESPN. Your session cookies may "
                "have expired or been mistyped — restart the app to be "
                "prompted for fresh SWID/espn_s2 values."
            ) from exc
        return cls(league)
```

Update `app/web/routes/dashboard.py`:

```python
# app/web/routes/dashboard.py
from fastapi import APIRouter, Depends, Request

from app.espn_client import EspnAuthError
from app.models import Player, Team
from app.sync import sync_all
from app.web.app import get_session

router = APIRouter()


@router.get("/")
def dashboard(request: Request, session=Depends(get_session)):
    teams = session.query(Team).order_by(Team.wins.desc()).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "dashboard.html",
                                       {"teams": teams})


@router.post("/sync")
def refresh(request: Request, session=Depends(get_session)):
    templates = request.app.state.templates
    espn_client = request.app.state.espn_client_factory()
    stats_client = request.app.state.stats_client_factory()
    try:
        result = sync_all(session, espn_client, stats_client,
                           request.app.state.season_year)
    except EspnAuthError as exc:
        return templates.TemplateResponse(request, "partials/error_banner.html",
                                           {"message": str(exc)})
    return templates.TemplateResponse(request, "partials/sync_status.html",
                                       {"result": result})


@router.get("/debug/unmatched")
def debug_unmatched(request: Request, session=Depends(get_session)):
    unmatched = session.query(Player).filter(Player.gsis_id.is_(None)).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "debug_unmatched.html",
                                       {"players": unmatched})
```

```html
<!-- app/web/templates/partials/error_banner.html -->
<div class="error-banner">
    <strong>Sync failed:</strong> {{ message }}
</div>
```

```html
<!-- app/web/templates/debug_unmatched.html -->
{% extends "base.html" %}
{% block content %}
<h1>Unmatched Players</h1>
<p>These ESPN players couldn't be matched to an nflverse stats ID, so their
   weekly stats and projections may be incomplete.</p>
<ul>
    {% for player in players %}
    <li>{{ player.name }} ({{ player.position }}, {{ player.pro_team }})</li>
    {% endfor %}
</ul>
{% endblock %}
```

Add to `app/web/static/style.css`:

```css
.error-banner { background: #fdd; border: 1px solid #c00; padding: 0.75rem; }
```

Append to `README.md`:

```markdown

## Troubleshooting

**"Sync failed: Could not authenticate with ESPN"** — Your `SWID`/`espn_s2`
cookies expired or were mistyped. Stop the app (Ctrl+C) and run
`python run.py` again — it will prompt you for fresh cookie values, with
instructions on where to find them in your browser.

**A player's stats look wrong or missing** — check `/debug/unmatched` in the
dashboard; it lists ESPN players that couldn't be matched to nflverse stats.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_dashboard.py -v`
Expected: PASS (all tests, including the two new ones)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: All tests across every module PASS.

- [ ] **Step 6: Commit**

```bash
git add app/espn_client.py app/web/routes/dashboard.py app/web/templates/partials/error_banner.html app/web/templates/debug_unmatched.html app/web/static/style.css tests/test_web_dashboard.py README.md
git commit -m "feat: add ESPN auth error handling and unmatched-players debug view"
```

---

## Final Verification

After Task 16, do a manual end-to-end run against your real league:

1. Fill in `.env` with your real ESPN cookies and league info.
2. `python run.py`
3. Click "Refresh Data" on the dashboard, confirm real teams/players/stats show up.
4. Visit `/trades`, `/waiver`, `/lineup`, `/analytics` and sanity-check the numbers against what you know about your league.
5. Check `/debug/unmatched` — investigate any unexpected unmatched players (usually rare edge cases like recently-signed free agents).
