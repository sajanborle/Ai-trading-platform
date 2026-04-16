from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, RedirectResponse

from bot import (
    analyze_symbol,
    generate_option_ideas,
    generate_trade_ideas,
    get_market_overview,
    get_news_for_symbol,
    get_option_contract_suggestions,
    get_stock_list,
    get_token,
)
from upstox import generate_token, get_connection_status, get_login_url, place_market_order

app = FastAPI(title="AI Trading Assistant")


@app.get("/")
def home():
    return FileResponse("templates/dashboard.html")


@app.get("/login")
def login():
    return RedirectResponse(get_login_url())


@app.get("/callback")
def callback(code: str):
    generate_token(code)
    return RedirectResponse(url="/")


@app.get("/api/status")
def status():
    return {"upstox": get_connection_status()}


@app.get("/stocks")
def stocks(segment: str = Query(default="all", pattern="^(all|equity|fno)$")):
    return {"results": get_stock_list(segment=segment)}


@app.get("/analyze")
def analyze(symbol: str, budget: int = 500):
    try:
        return analyze_symbol(symbol=symbol.upper(), budget=budget)
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unable to analyze {symbol}", "details": str(exc)}


@app.get("/trade-ideas")
def trade_ideas(
    budget: int = 500,
    segment: str = Query(default="all", pattern="^(all|equity|fno)$"),
    limit: int = 6,
):
    return {
        "budget": budget,
        "segment": segment,
        "results": generate_trade_ideas(budget=budget, segment=segment, limit=limit),
    }


@app.get("/option-ideas")
def option_ideas(budget: int = 500, limit: int = 6):
    return {
        "budget": budget,
        "results": generate_option_ideas(budget=budget, limit=limit),
    }


@app.get("/option-ideas/{symbol}")
def option_ideas_for_symbol(symbol: str, budget: int = 500, limit: int = 4):
    return get_option_contract_suggestions(symbol=symbol.upper(), budget=budget, limit=limit)


@app.get("/news/{symbol}")
def news_for_symbol(symbol: str):
    return get_news_for_symbol(symbol)


@app.get("/scanner")
def scanner(budget: int = 500):
    return {"results": generate_trade_ideas(budget=budget, segment="all", limit=8)}


@app.get("/suggest")
def suggest(budget: int = 500):
    return {"results": generate_trade_ideas(budget=budget, segment="equity", limit=5)}


@app.get("/under500")
def under500():
    ideas = generate_trade_ideas(budget=500, segment="equity", limit=12)
    filtered = [idea for idea in ideas if idea["price"] <= 500]
    return {"results": filtered}


@app.get("/market-overview")
def market_overview():
    return get_market_overview()


@app.post("/buy")
def buy(symbol: str, qty: int):
    instrument = get_token(symbol.upper())
    if not instrument:
        return {"error": "Invalid symbol"}
    if qty < 1:
        return {"error": "Quantity must be at least 1"}
    return place_market_order(symbol=symbol.upper(), qty=qty, instrument_token=instrument)
