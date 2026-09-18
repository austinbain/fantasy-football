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

    from app.web.routes.trades import router as trades_router
    app.include_router(trades_router)

    from app.web.routes.waiver import router as waiver_router
    app.include_router(waiver_router)

    return app


def get_session(request: Request):
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
