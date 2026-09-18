import os

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


def test_load_config_never_reads_espn_cookies_from_file(tmp_path, monkeypatch):
    # Even if a stray .env has cookie values in it (e.g. a leftover from
    # an older setup), Config must not surface them, AND they must never
    # be loaded into the process environment where get_espn_credentials()
    # would silently pick them up.
    monkeypatch.delenv("ESPN_SWID", raising=False)
    monkeypatch.delenv("ESPN_S2", raising=False)
    env_path = write_env(tmp_path, ESPN_SWID="{SHOULD-BE-IGNORED}")
    config = load_config(str(env_path))
    assert not hasattr(config, "espn_swid")
    assert os.environ.get("ESPN_SWID") is None


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
