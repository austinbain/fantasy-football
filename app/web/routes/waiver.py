from fastapi import APIRouter, Depends, Request

from app.analytics.waiver import rank_waiver_wire
from app.web.app import get_session

router = APIRouter()


@router.get("/waiver")
def waiver_page(request: Request, session=Depends(get_session)):
    candidates = rank_waiver_wire(
        session, request.app.state.my_team_id,
        request.app.state.season_year, week=1,
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "waiver.html",
                                       {"candidates": candidates})
