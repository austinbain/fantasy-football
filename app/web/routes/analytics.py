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
