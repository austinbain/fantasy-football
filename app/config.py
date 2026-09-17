import getpass
import os
from dataclasses import dataclass

from dotenv import load_dotenv, dotenv_values

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
    # First read what's in the file to check for required vars
    file_vars = dotenv_values(env_path)
    missing = [key for key in REQUIRED_VARS if key not in file_vars]
    if missing:
        raise ConfigError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    # Then load the file into os.environ
    load_dotenv(env_path, override=True)
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
