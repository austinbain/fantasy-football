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
