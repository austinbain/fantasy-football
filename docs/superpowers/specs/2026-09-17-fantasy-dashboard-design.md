# ESPN Fantasy Football Insights Dashboard — Design

Date: 2026-09-17
Status: Approved for planning

## Overview

A local, on-demand web dashboard that pulls data from a private ESPN
Fantasy Football league and surfaces insights to help with trades,
waiver-wire pickups, weekly lineups, and overall league strategy. Run
with a single command; no hosting, no accounts beyond your own ESPN
login cookies.

## Goals

- Trade analyzer: value both sides of a proposed trade, flag lopsided
  deals, suggest plausible trade targets based on roster
  surplus/need across the league.
- Waiver wire recommendations: rank available free agents by
  projected value and fit for your team's needs.
- Start/sit & lineup optimizer: weekly lineup recommendations using
  projections, matchup difficulty, and injury status.
- League/team analytics: power rankings, strength of schedule, luck
  (points-for vs. record), simple rest-of-season standings
  projection.
- Better-than-ESPN player projections, built from free/legitimate
  data (no ToS-violating scraping of paid ranking sites).

## Non-goals

- Multi-user hosting, accounts, or auth beyond your own ESPN cookies.
- Support for leagues other than the user's own (single league/single
  season configured via `.env`, though the schema doesn't preclude
  more later).
- Real-time/live-scoring features (in-game win probability, etc.).
- Mobile app or offline packaging — a locally-run web server is
  sufficient.

## Architecture

Single Python 3.11+ process:

- **FastAPI** for the web server and routes.
- **SQLite** as a local cache (via SQLAlchemy) so pages render from
  cached data instead of hitting ESPN/nflverse on every request.
- **Jinja2 + HTMX** for server-rendered pages with light
  interactivity (form submissions, partial page updates) — no
  separate frontend build step.
- **`espn_api`** (community package) for ESPN Fantasy data: league
  settings, teams, rosters, matchups, free agents, transaction
  history. Authenticates via `SWID` and `espn_s2` cookies (required
  for private leagues).
- **nflverse public data files**, read directly via `pandas.read_parquet`/
  `read_csv` against nflverse's published release URLs (weekly player
  stats, including each player's opponent for the week) and the
  `dynastyprocess/data` player-ID crosswalk (for matching ESPN player
  IDs to nflverse's) — used to build custom projections instead of
  relying on ESPN's own weak projections or scraping a paid ranking
  service. (The `nfl_data_py` convenience package was evaluated but
  dropped: it pins `numpy<2.0`, which has no prebuilt wheel for modern
  Python and requires a C build toolchain most users won't have
  installed; it's a thin wrapper around the same public URLs, so
  reading them directly gets the same data without that dependency.)
- **`run.py`** as the entry point: starts uvicorn and opens the
  default browser to `http://localhost:<port>`.
- **`.env`** (gitignored) holds only non-sensitive config —
  `ESPN_LEAGUE_ID`, `ESPN_SEASON_YEAR`, `MY_TEAM_ID`. ESPN session
  cookies (`SWID`, `espn_s2`) are never written to `.env` or any file:
  `run.py` prompts for them interactively on each launch (with
  instructions on finding them), falling back to `ESPN_SWID`/`ESPN_S2`
  shell environment variables if already set for the session.

## Data flow

1. On startup or when the user clicks "Refresh Data," `sync.py` calls
   `espn_client` and `stats_client`, normalizes the results, and
   writes/updates rows in SQLite.
2. Analytics modules (`trade_analyzer`, `waiver`, `lineup`,
   `power_rankings`) read from SQLite and compute results on demand
   when a page loads — fast, since it's a local read, not a live API
   call.
3. FastAPI routes render Jinja templates with the computed results.
   HTMX handles in-page interactions (e.g., submitting a trade
   scenario, re-sorting the waiver table) via partial-page swaps
   instead of full reloads.

No background scheduler — refresh is a manual, explicit action,
matching the "run it when I need it" usage pattern.

## Components

```
fantasy-nfl/
  app/
    config.py            # loads .env, validates required vars
    espn_client.py        # espn_api wrapper: league/team/roster/FA/transactions
    stats_client.py        # direct nflverse/dynastyprocess file reads: weekly stats, DvP, ID crosswalk
    projections.py         # season avg + recent-form + matchup-adjusted projection
    models.py              # SQLAlchemy models (players, weekly_stats, rosters, teams)
    sync.py                 # refresh job: pulls ESPN + nflverse into SQLite
    analytics/
      trade_analyzer.py    # trade valuation + suggested targets
      waiver.py             # free-agent ranking by value + team need
      lineup.py             # start/sit recommendations
      power_rankings.py    # power rankings, SoS, luck, standings projection
    web/
      routes/              # FastAPI routers per feature page
      templates/            # Jinja2 templates
      static/                # CSS, minimal JS, HTMX
  tests/
    fixtures/                # recorded sample ESPN/nflverse responses
    test_projections.py
    test_trade_analyzer.py
    test_waiver.py
    test_lineup.py
    test_power_rankings.py
  run.py
  .env.example
  requirements.txt
  README.md
```

### `projections.py`

Player projection = weighted blend of:
- Season-to-date per-game average.
- Last-3-week trend (recency weighting).
- Opponent adjustment: points allowed to the player's position by
  the upcoming opponent, relative to league average.

The formula is intentionally simple and inspectable (not a black-box
model) so trade/waiver/lineup recommendations can show *why* a player
is rated the way they are.

### `trade_analyzer.py`

- Input: two (or more) sets of players/picks being swapped.
- Values each side using `projections.py` output plus a positional
  scarcity multiplier (e.g., a top-5 RB is worth more than raw points
  alone suggest, given replacement-level dropoff at the position).
- Flags trades where one side's total value exceeds the other by a
  configurable threshold.
- "Suggest trades" mode: cross-references your roster's surplus
  positions against other teams' rosters to propose plausible,
  mutually beneficial swaps.

### `waiver.py`

- Lists all free agents, ranked by projection + a need multiplier
  based on gaps/weakness in your current roster at that position.

### `lineup.py`

- For each roster slot, compares eligible players by projection,
  matchup, and injury/bye status, and recommends a starting lineup.

### `power_rankings.py`

- Power ranking blends record, points-for, and points-against.
- Strength of schedule: average opponent win% or defensive strength,
  past and remaining.
- Luck metric: compares actual record to a record derived purely
  from points-for rank each week (i.e., would this team be winning
  if scores were shuffled across the league).
- Standings projection: simple Monte Carlo simulation of remaining
  games using team scoring distributions.

## Error handling

- **Expired/invalid ESPN cookies**: caught at the `espn_client` level,
  surfaced as a dashboard-wide banner telling the user to restart the
  app, which re-prompts for fresh `SWID`/`espn_s2` values with
  instructions on finding them.
- **nflverse data unavailable** (very early season, bye weeks, data
  lag): `projections.py` falls back to ESPN-only inputs rather than
  failing.
- **Unmatched players** between ESPN player IDs and nflverse GSIS
  IDs: best-effort name+team matching, with a `/debug/unmatched`
  view listing anything that didn't resolve, instead of silently
  dropping or crashing.

## Testing

- Unit tests (pytest) for the modules with real logic: projections,
  trade valuation, waiver ranking, lineup recommendation, power
  rankings — run against recorded fixture data, not live API calls.
- The ESPN/nflverse integration layer itself is verified manually by
  running the live dashboard against the user's real league (a
  personal tool talking to a live third-party API isn't practical to
  fully mock in CI).

## Setup requirements (user-provided)

- ESPN league ID and season year.
- The user's team ID within the league.
- `SWID` and `espn_s2` cookie values, entered interactively when the
  app starts (instructions to extract these from browser dev tools
  are printed at the prompt and included in the README). Never stored
  in `.env` or any other file.

## Open questions / future work (explicitly out of scope for v1)

- Historical multi-season trend analysis (v1 is current-season only).
- Notifications (email/Slack/Discord) — noted as a possible future
  automated-report mode, not part of this build.
- Support for leagues beyond the user's own.
