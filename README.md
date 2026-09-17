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
