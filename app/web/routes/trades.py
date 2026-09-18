from fastapi import APIRouter, Depends, Form, Request

from app.models import Player, Team
from app.analytics.trade_analyzer import TradeSide, evaluate_trade, suggest_trades
from app.web.app import get_session

router = APIRouter()


@router.get("/trades")
def trades_page(request: Request, session=Depends(get_session)):
    teams = session.query(Team).all()
    rosters = {
        team.id: session.query(Player).filter_by(team_id=team.id).all()
        for team in teams
    }
    my_team_id = request.app.state.my_team_id
    current_week = request.app.state.current_week
    suggestions = suggest_trades(session, my_team_id,
                                  request.app.state.season_year, week=current_week)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "trades.html", {
        "teams": teams, "rosters": rosters, "suggestions": suggestions,
        "current_week": current_week,
    })


@router.post("/trades/evaluate")
def evaluate_trade_route(
    request: Request,
    side_a_players: list[str] = Form(default=[]),
    side_b_players: list[str] = Form(default=[]),
    week: int = Form(...),
    session=Depends(get_session),
):
    templates = request.app.state.templates
    if not side_a_players or not side_b_players:
        return templates.TemplateResponse(request, "partials/trade_result.html", {
            "error": "Select at least one player for each side.",
        })
    try:
        side_a = TradeSide(team_id=0, player_ids=[int(p) for p in side_a_players])
        side_b = TradeSide(team_id=0, player_ids=[int(p) for p in side_b_players])
        result = evaluate_trade(session, side_a, side_b,
                                 request.app.state.season_year, week)
    except (ValueError, AttributeError):
        return templates.TemplateResponse(request, "partials/trade_result.html", {
            "error": "One or more selected players could not be found. Please try again.",
        })
    return templates.TemplateResponse(request, "partials/trade_result.html",
                                       {"result": result})
