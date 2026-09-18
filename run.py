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
