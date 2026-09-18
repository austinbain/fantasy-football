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
