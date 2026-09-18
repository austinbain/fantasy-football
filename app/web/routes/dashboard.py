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
    try:
        espn_client = request.app.state.espn_client_factory()
        stats_client = request.app.state.stats_client_factory()
        result = sync_all(session, espn_client, stats_client,
                           request.app.state.season_year)
    except EspnAuthError as exc:
        return templates.TemplateResponse(request, "partials/error_banner.html",
                                           {"message": str(exc)})
    request.app.state.current_week = result.current_week
    return templates.TemplateResponse(request, "partials/sync_status.html",
                                       {"result": result})


@router.get("/debug/unmatched")
def debug_unmatched(request: Request, session=Depends(get_session)):
    unmatched = session.query(Player).filter(Player.gsis_id.is_(None)).all()
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "debug_unmatched.html",
                                       {"players": unmatched})
