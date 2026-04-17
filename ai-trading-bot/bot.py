from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import yfinance as yf

from upstox import fetch_option_chain, fetch_option_contracts, refresh_token

def _get_yfinance_cache_dir() -> str:
    if os.getenv("VERCEL"):
        return "/tmp/yf-cache"
    return str(Path(__file__).resolve().parent / ".yf-cache")


os.environ.setdefault("YFINANCE_CACHE_DIR", _get_yfinance_cache_dir())
Path(os.environ["YFINANCE_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
yf.set_tz_cache_location(os.environ["YFINANCE_CACHE_DIR"])

TOP_50_STOCKS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT",
    "AXISBANK", "KOTAKBANK", "BAJFINANCE", "MARUTI", "ASIANPAINT", "HINDUNILVR",
    "ULTRACEMCO", "WIPRO", "TECHM", "TITAN", "SUNPHARMA", "POWERGRID",
    "NESTLEIND", "NTPC", "ONGC", "TATASTEEL", "JSWSTEEL", "ADANIENT",
    "ADANIPORTS", "BAJAJFINSV", "BRITANNIA", "CIPLA", "COALINDIA",
    "DIVISLAB", "DRREDDY", "EICHERMOT", "GRASIM", "HCLTECH", "HEROMOTOCO",
    "HINDALCO", "INDUSINDBK", "M&M", "SBILIFE", "SHREECEM",
    "SIEMENS", "TATACONSUM", "TATAMOTORS", "UPL", "VEDL", "AMBUJACEM",
]

# FNO_STOCKS = {
#     "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC", "LT",
#     "AXISBANK", "KOTAKBANK", "BAJFINANCE", "MARUTI", "ASIANPAINT", "HINDUNILVR",
#     "ULTRACEMCO", "WIPRO", "TECHM", "TITAN", "SUNPHARMA", "POWERGRID",
#     "NTPC", "ONGC", "TATASTEEL", "JSWSTEEL", "ADANIENT", "ADANIPORTS",
#     "BAJAJFINSV", "CIPLA", "COALINDIA", "DRREDDY", "GRASIM", "HCLTECH",
#     "HEROMOTOCO", "HINDALCO", "INDUSINDBK", "M&M", "SBILIFE",
#     "SIEMENS", "TATACONSUM", "TATAMOTORS", "UPL",
# }

POSITIVE_NEWS_WORDS = {
    "profit", "growth", "upgrade", "surge", "beat", "record", "bullish",
    "expands", "wins", "strong", "buy", "breakout", "order", "approval",
}
NEGATIVE_NEWS_WORDS = {
    "loss", "fall", "downgrade", "drop", "miss", "weak", "bearish",
    "penalty", "probe", "decline", "sell", "fraud", "lawsuit", "crash",
}

NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_URL = os.getenv("NEWS_API_URL", "https://newsapi.org/v2/everything")


def _fallback_instruments() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": TOP_50_STOCKS,
            "instrument_token": TOP_50_STOCKS,
            "segment": ["FNO" if symbol in FNO_STOCKS else "EQUITY" for symbol in TOP_50_STOCKS],
        }
    )


def load_instruments() -> pd.DataFrame:
    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"

    try:
        df = pd.read_csv(url)
        df = df[
            (df["exchange"] == "NSE_EQ")
            & (df["instrument_type"] == "EQUITY")
            & (df["tradingsymbol"].isin(TOP_50_STOCKS))
        ].copy()
        df["symbol"] = df["tradingsymbol"]
        df["instrument_token"] = df["instrument_key"]
        df["segment"] = df["symbol"].apply(lambda symbol: "FNO" if symbol in FNO_STOCKS else "EQUITY")
        return df[["symbol", "instrument_token", "segment"]].sort_values("symbol").reset_index(drop=True)
    except Exception as exc:
        print(f"Instrument load fallback active: {exc}")
        return _fallback_instruments()


INSTRUMENTS = load_instruments()


def _ticker(symbol: str) -> str:
    return f"{symbol}.NS"


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".NS", "")


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def _pct_change(current: float, previous: float) -> float:
    if not previous:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def is_fno_symbol(symbol: str) -> bool:
    return symbol in FNO_STOCKS


def get_token(symbol: str) -> Optional[str]:
    row = INSTRUMENTS[INSTRUMENTS["symbol"] == symbol]
    if row.empty:
        return None
    return str(row.iloc[0]["instrument_token"])


def get_live_price(instrument_token: str, symbol: Optional[str] = None) -> Optional[float]:
    token = refresh_token()
    if token and instrument_token and instrument_token != symbol:
        url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={instrument_token}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            res = requests.get(url, headers=headers, timeout=8).json()
            price = list(res["data"].values())[0]["last_price"]
            return _safe_float(price, default=0.0) or None
        except Exception:
            pass

    if not symbol:
        return None

    try:
        history = yf.Ticker(_ticker(symbol)).history(period="5d", auto_adjust=False)
        if history.empty:
            return None
        return _safe_float(history["Close"].dropna().iloc[-1], default=0.0) or None
    except Exception:
        return None


@lru_cache(maxsize=128)
def get_price_history(symbol: str, period: str = "6mo") -> pd.DataFrame:
    symbol = normalize_symbol(symbol)
    history = yf.Ticker(_ticker(symbol)).history(period=period, interval="1d", auto_adjust=False)
    if history.empty:
        raise ValueError(f"No historical data for {symbol}")
    return history.dropna().copy()


def get_stock_list(segment: str = "all") -> list[dict]:
    df = INSTRUMENTS.copy()
    if segment == "fno":
        df = df[df["segment"] == "FNO"]
    elif segment == "equity":
        df = df[df["segment"] == "EQUITY"]

    return [
        {
            "symbol": row["symbol"],
            "instrument_token": row["instrument_token"],
            "segment": row["segment"],
            "is_fno": row["segment"] == "FNO",
        }
        for _, row in df.iterrows()
    ]


def _score_headlines(headlines: list[str]) -> tuple[int, str]:
    score = 0
    for title in headlines:
        lower_title = title.lower()
        score += sum(1 for word in POSITIVE_NEWS_WORDS if word in lower_title)
        score -= sum(1 for word in NEGATIVE_NEWS_WORDS if word in lower_title)

    if score >= 2:
        label = "Positive"
    elif score <= -2:
        label = "Negative"
    else:
        label = "Neutral"

    return score, label


def _newsapi_articles(symbol: str) -> list[dict]:
    if not NEWS_API_KEY:
        return []

    params = {
        "q": f'"{symbol}" AND (stock OR shares OR earnings OR results OR nse)',
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5,
        "searchIn": "title,description",
    }
    headers = {"X-Api-Key": NEWS_API_KEY}

    response = requests.get(NEWS_API_URL, params=params, headers=headers, timeout=8)
    payload = response.json()
    articles = payload.get("articles", [])

    return [
        {
            "title": article.get("title") or "Untitled",
            "source": (article.get("source") or {}).get("name", "News API"),
            "url": article.get("url"),
            "published_at": article.get("publishedAt"),
            "summary": article.get("description") or "",
        }
        for article in articles[:5]
    ]


def _rss_articles(symbol: str) -> list[dict]:
    query = quote(f"{symbol} stock India NSE")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

    response = requests.get(url, timeout=6)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    articles = []
    for item in root.findall(".//item")[:5]:
        articles.append(
            {
                "title": item.findtext("title", default="Untitled"),
                "source": "Google News RSS",
                "url": item.findtext("link", default=""),
                "published_at": item.findtext("pubDate", default=""),
                "summary": item.findtext("description", default=""),
            }
        )
    return articles


def get_news_sentiment(symbol: str) -> dict:
    symbol = normalize_symbol(symbol)
    try:
        articles = _newsapi_articles(symbol)
        provider = "NewsAPI"
        if not articles:
            articles = _rss_articles(symbol)
            provider = "Google News RSS"

        if not articles:
            raise ValueError("No headlines found")

        titles = [article["title"] for article in articles]
        score, label = _score_headlines(titles)

        return {
            "label": label,
            "score": score,
            "headline": articles[0]["title"],
            "source": provider,
            "articles": articles[:3],
            "api_configured": bool(NEWS_API_KEY),
        }
    except Exception:
        return {
            "label": "Neutral",
            "score": 0,
            "headline": "Live news feed unavailable, technical data used.",
            "source": "Fallback",
            "articles": [],
            "api_configured": bool(NEWS_API_KEY),
        }


def ai_decision(symbol: str, budget: int = 500) -> dict:
    symbol = normalize_symbol(symbol)
    history = get_price_history(symbol)
    close = history["Close"]
    high = history["High"]
    low = history["Low"]
    volume = history["Volume"]

    latest_price = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else latest_price

    sma20 = float(close.tail(20).mean())
    sma50 = float(close.tail(50).mean())
    avg_volume20 = float(volume.tail(20).mean())
    current_volume = float(volume.iloc[-1])
    momentum_5d = _pct_change(latest_price, float(close.iloc[-6]) if len(close) > 5 else prev_close)
    daily_change = _pct_change(latest_price, prev_close)

    delta = close.diff()
    gains = delta.clip(lower=0).tail(14).mean()
    losses = (-delta.clip(upper=0)).tail(14).mean()
    rs = gains / losses if losses else 999
    rsi = 100 - (100 / (1 + rs))

    atr = float((high.tail(14) - low.tail(14)).mean())
    support = float(low.tail(10).min())
    resistance = float(high.tail(10).max())

    score = 50
    reasons = []

    if latest_price > sma20:
        score += 8
        reasons.append("price above 20 DMA")
    else:
        score -= 8
        reasons.append("price below 20 DMA")

    if sma20 > sma50:
        score += 10
        reasons.append("short-term trend stronger than medium trend")
    else:
        score -= 10
        reasons.append("trend still weak")

    if momentum_5d > 2:
        score += 10
        reasons.append("5-day momentum positive")
    elif momentum_5d < -2:
        score -= 10
        reasons.append("5-day momentum negative")

    if 45 <= rsi <= 68:
        score += 8
        reasons.append("RSI in healthy swing zone")
    elif rsi > 75:
        score -= 8
        reasons.append("RSI overbought")
    elif rsi < 35:
        score -= 5
        reasons.append("RSI weak")

    if current_volume > avg_volume20 * 1.1:
        score += 6
        reasons.append("volume is supporting the move")

    news = get_news_sentiment(symbol)
    score += max(min(news["score"] * 2, 8), -8)
    reasons.append(f"news bias {news['label'].lower()}")

    score = max(0, min(100, score))

    if score >= 72:
        decision = "STRONG BUY"
        setup = "Momentum breakout"
    elif score >= 60:
        decision = "BUY"
        setup = "Swing long"
    elif score >= 48:
        decision = "WATCH"
        setup = "Wait for confirmation"
    else:
        decision = "AVOID"
        setup = "Weak structure"

    stop_loss = latest_price - max(atr * 1.2, latest_price * 0.015)
    if support and support < latest_price:
        stop_loss = max(stop_loss, support * 0.995)
    stop_loss = min(stop_loss, latest_price * 0.985)

    target = latest_price + max(atr * 2.0, latest_price * 0.03)
    if resistance and resistance > latest_price:
        target = max(target, resistance)

    stop_loss = round(max(stop_loss, latest_price * 0.9), 2)
    target = round(max(target, latest_price * 1.02), 2)

    risk = max(latest_price - stop_loss, 0.01)
    reward = max(target - latest_price, 0.01)
    risk_reward = round(reward / risk, 2)
    qty = int(budget // latest_price) if latest_price > 0 else 0
    capital_required = round(qty * latest_price, 2)

    return {
        "symbol": symbol,
        "segment": "FNO" if is_fno_symbol(symbol) else "EQUITY",
        "is_fno": is_fno_symbol(symbol),
        "price": round(latest_price, 2),
        "previous_close": round(prev_close, 2),
        "daily_change_pct": daily_change,
        "momentum_5d": momentum_5d,
        "sma20": round(sma20, 2),
        "sma50": round(sma50, 2),
        "rsi": round(float(rsi), 2),
        "atr": round(atr, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "decision": decision,
        "setup": setup,
        "score": score,
        "confidence": score,
        "stop_loss": stop_loss,
        "target": target,
        "risk_reward": risk_reward,
        "qty": qty,
        "capital_required": capital_required,
        "can_buy_with_budget": qty >= 1,
        "reason": ", ".join(reasons[:4]),
        "news_sentiment": news["label"],
        "headline": news["headline"],
        "news_source": news["source"],
        "news_api_configured": news["api_configured"],
        "news_articles": news["articles"],
    }


def analyze_symbol(symbol: str, budget: int = 500) -> dict:
    symbol = normalize_symbol(symbol)
    analysis = ai_decision(symbol, budget=budget)
    token = get_token(symbol)
    live_price = get_live_price(token or symbol, symbol=symbol)

    if live_price:
        analysis["live_price"] = live_price
        analysis["price"] = live_price
        analysis["daily_change_pct"] = _pct_change(live_price, analysis["previous_close"])

    return analysis


def get_personal_stock_plan(symbol: str, capital: int = 500, risk_profile: str = "low") -> dict:
    symbol = normalize_symbol(symbol)
    analysis = analyze_symbol(symbol=symbol, budget=capital)

    risk_profile = risk_profile.lower()
    risk_fraction = {"low": 0.02, "medium": 0.04, "high": 0.06}.get(risk_profile, 0.02)
    per_share_risk = max(analysis["price"] - analysis["stop_loss"], 0.01)
    max_risk_amount = round(capital * risk_fraction, 2)
    qty_by_budget = int(capital // analysis["price"]) if analysis["price"] > 0 else 0
    qty_by_risk = int(max_risk_amount // per_share_risk) if per_share_risk > 0 else 0
    suggested_qty = max(min(qty_by_budget, qty_by_risk), 0)

    recommendation = "AVOID"
    if analysis["decision"] in {"STRONG BUY", "BUY"} and suggested_qty >= 1:
        recommendation = "BUY SMALL"
    elif analysis["decision"] == "WATCH":
        recommendation = "WAIT"

    monthly_goal_note = (
        "Small monthly side income is possible only with discipline; it is not guaranteed, and some months can be negative."
    )

    return {
        **analysis,
        "capital": capital,
        "risk_profile": risk_profile,
        "per_share_risk": round(per_share_risk, 2),
        "max_risk_amount": max_risk_amount,
        "qty_by_budget": qty_by_budget,
        "qty_by_risk": qty_by_risk,
        "suggested_qty": suggested_qty,
        "recommendation": recommendation,
        "entry_plan": f"Consider entry near Rs. {analysis['price']} only if price stays above stop-loss Rs. {analysis['stop_loss']}.",
        "exit_plan": f"Book profit near Rs. {analysis['target']} or exit below Rs. {analysis['stop_loss']}.",
        "monthly_goal_note": monthly_goal_note,
        "coach_note": (
            "As a beginner, use only cash equity and very small size. Avoid MTF and options until your journal shows consistency."
        ),
        "verdict_reason": (
            f"Decision {analysis['decision']}, score {analysis['score']}, news {analysis['news_sentiment']}, "
            f"and risk-reward {analysis['risk_reward']}."
        ),
    }


def generate_trade_ideas(budget: int = 500, segment: str = "all", limit: int = 6) -> list[dict]:
    symbols = TOP_50_STOCKS
    if segment == "fno":
        symbols = [symbol for symbol in TOP_50_STOCKS if symbol in FNO_STOCKS]
    elif segment == "equity":
        symbols = [symbol for symbol in TOP_50_STOCKS if symbol not in FNO_STOCKS]

    ideas = []
    for symbol in symbols:
        try:
            idea = analyze_symbol(symbol, budget=budget)
        except Exception:
            continue

        if idea["decision"] == "AVOID":
            continue

        if not idea["can_buy_with_budget"] and segment != "fno":
            continue

        ideas.append(idea)

    ideas.sort(
        key=lambda item: (
            item["decision"] == "STRONG BUY",
            item["decision"] == "BUY",
            item["score"],
            item["risk_reward"],
        ),
        reverse=True,
    )
    return ideas[:limit]


def generate_beginner_ideas(budget: int = 500, limit: int = 6) -> list[dict]:
    ideas = generate_trade_ideas(budget=budget, segment="equity", limit=20)
    beginner = []

    for idea in ideas:
        if idea["price"] > 500:
            continue
        if idea["decision"] not in {"STRONG BUY", "BUY", "WATCH"}:
            continue

        action = "Wait"
        if idea["decision"] in {"STRONG BUY", "BUY"} and idea["risk_reward"] >= 1.5:
            action = "Buy small"
        elif idea["decision"] == "WATCH":
            action = "Watch only"

        beginner.append(
            {
                **idea,
                "beginner_action": action,
                "why_this_stock": (
                    f"Price under Rs. 500, trend score {idea['score']}, "
                    f"and stop-loss clearly defined at Rs. {idea['stop_loss']}."
                ),
                "how_to_buy": "Buy only 1 quantity first, then observe price movement calmly.",
                "when_to_sell": (
                    f"Exit near target Rs. {idea['target']} or exit fast if price closes below stop-loss Rs. {idea['stop_loss']}."
                ),
                "profit_booking": "If stock moves 3% to 5% up quickly, you can book partial or full profit.",
            }
        )

    beginner.sort(
        key=lambda item: (
            item["beginner_action"] == "Buy small",
            item["score"],
            item["risk_reward"],
        ),
        reverse=True,
    )
    return beginner[:limit]


def _normalize_option_rows(payload: dict) -> list[dict]:
    rows = payload.get("data", [])
    if isinstance(rows, dict):
        rows = list(rows.values())
    return rows if isinstance(rows, list) else []


def _extract_option_leg(row: dict, side: str) -> dict:
    leg = row.get(side) or {}
    market_data = leg.get("market_data") or {}
    greeks = leg.get("option_greeks") or {}
    return {
        "instrument_key": leg.get("instrument_key") or row.get(f"{side}_instrument_key"),
        "trading_symbol": leg.get("trading_symbol") or row.get(f"{side}_trading_symbol"),
        "ltp": _safe_float(market_data.get("ltp") or leg.get("ltp"), default=0.0),
        "oi": int((market_data.get("oi") or leg.get("oi") or 0)),
        "volume": int((market_data.get("volume") or leg.get("volume") or 0)),
        "delta": _safe_float(greeks.get("delta") or leg.get("delta"), default=0.0),
        "theta": _safe_float(greeks.get("theta") or leg.get("theta"), default=0.0),
        "gamma": _safe_float(greeks.get("gamma") or leg.get("gamma"), default=0.0),
        "iv": _safe_float(greeks.get("iv") or leg.get("iv"), default=0.0),
    }


def get_option_contract_suggestions(symbol: str, budget: int = 500, limit: int = 4) -> dict:
    symbol = symbol.upper()
    if not is_fno_symbol(symbol):
        return {
            "symbol": symbol,
            "results": [],
            "error": "This stock is not marked as F&O eligible in the current shortlist.",
        }

    instrument_key = get_token(symbol)
    if not instrument_key:
        return {"symbol": symbol, "results": [], "error": "Underlying instrument key not found."}

    option_contracts = fetch_option_contracts(instrument_key)
    contract_rows = _normalize_option_rows(option_contracts)
    expiries = sorted({row.get("expiry") or row.get("expiry_date") for row in contract_rows if row.get("expiry") or row.get("expiry_date")})
    nearest_expiry = expiries[0] if expiries else None

    if not nearest_expiry:
        return {
            "symbol": symbol,
            "results": [],
            "error": option_contracts.get("error", "No option expiries received from Upstox."),
        }

    chain_payload = fetch_option_chain(instrument_key, nearest_expiry)
    chain_rows = _normalize_option_rows(chain_payload)
    if not chain_rows:
        return {
            "symbol": symbol,
            "expiry": nearest_expiry,
            "results": [],
            "error": chain_payload.get("error", "No option chain data received."),
        }

    underlying = analyze_symbol(symbol, budget=budget)
    bullish_bias = underlying["decision"] in {"STRONG BUY", "BUY"}
    preferred_side = "call_options" if bullish_bias else "put_options"
    bias_label = "Bullish CE" if bullish_bias else "Bearish PE"
    target_delta = 0.35 if bullish_bias else -0.35

    ideas = []
    for row in chain_rows:
        strike = _safe_float(row.get("strike_price") or row.get("strike"), default=0.0)
        side_data = _extract_option_leg(row, preferred_side)
        if not side_data["instrument_key"] or side_data["ltp"] <= 0:
            continue

        lot_size = int(row.get("lot_size") or side_data.get("lot_size") or 1)
        estimated_cost = round(side_data["ltp"] * lot_size, 2)
        delta_gap = abs(abs(side_data["delta"]) - abs(target_delta))
        liquidity_score = min(side_data["oi"] / 100000, 1.0) * 10 + min(side_data["volume"] / 50000, 1.0) * 10
        affordability_score = 8 if estimated_cost <= budget * 3 else 3
        score = round((10 - min(delta_gap * 20, 10)) + liquidity_score + affordability_score, 2)

        stop_loss = round(side_data["ltp"] * 0.72, 2)
        target = round(side_data["ltp"] * 1.4, 2)
        risk_reward = round((target - side_data["ltp"]) / max(side_data["ltp"] - stop_loss, 0.01), 2)

        ideas.append(
            {
                "symbol": symbol,
                "bias": bias_label,
                "expiry": nearest_expiry,
                "strike": strike,
                "option_type": "CE" if bullish_bias else "PE",
                "contract_symbol": side_data["trading_symbol"] or f"{symbol} {strike}",
                "instrument_key": side_data["instrument_key"],
                "premium": side_data["ltp"],
                "lot_size": lot_size,
                "estimated_cost": estimated_cost,
                "delta": side_data["delta"],
                "theta": side_data["theta"],
                "gamma": side_data["gamma"],
                "iv": side_data["iv"],
                "oi": side_data["oi"],
                "volume": side_data["volume"],
                "score": score,
                "entry": side_data["ltp"],
                "stop_loss": stop_loss,
                "target": target,
                "risk_reward": risk_reward,
                "reason": f"{bias_label} setup with delta {side_data['delta']}, OI {side_data['oi']} and premium near tradable zone.",
                "underlying_view": underlying,
            }
        )

    ideas.sort(key=lambda item: (item["score"], item["oi"], item["volume"]), reverse=True)
    return {
        "symbol": symbol,
        "expiry": nearest_expiry,
        "underlying_price": underlying["price"],
        "underlying_decision": underlying["decision"],
        "results": ideas[:limit],
        "error": None if ideas else "Option chain available but no liquid contracts matched the filter.",
    }


def generate_option_ideas(budget: int = 500, limit: int = 6) -> list[dict]:
    candidates = generate_trade_ideas(budget=budget, segment="fno", limit=max(limit, 4))
    option_ideas = []
    for candidate in candidates:
        suggestion = get_option_contract_suggestions(candidate["symbol"], budget=budget, limit=2)
        option_ideas.extend(suggestion.get("results", []))

    option_ideas.sort(key=lambda item: (item["score"], item["risk_reward"]), reverse=True)
    return option_ideas[:limit]


def get_news_for_symbol(symbol: str) -> dict:
    news = get_news_sentiment(symbol.upper())
    return {
        "symbol": symbol.upper(),
        "provider": news["source"],
        "sentiment": news["label"],
        "score": news["score"],
        "headline": news["headline"],
        "api_configured": news["api_configured"],
        "articles": news["articles"],
    }


def get_beginner_playbook() -> dict:
    return {
        "goal": "First understand market basics, then place very small trades.",
        "steps": [
            {
                "title": "1. Market means ownership",
                "description": "When you buy a stock, you buy a small part of that company.",
            },
            {
                "title": "2. Buy only when plan is clear",
                "description": "Before buying, know your entry price, stop-loss and target.",
            },
            {
                "title": "3. Stop-loss protects capital",
                "description": "If price falls to stop-loss, exit. Small loss is normal and safe.",
            },
            {
                "title": "4. Profit booking is planned selling",
                "description": "When target hits or momentum becomes weak, book profit instead of waiting forever.",
            },
            {
                "title": "5. Start with delivery, not risky F&O",
                "description": "As a beginner, learn with cash equity first. Use F&O only after understanding risk well.",
            },
        ],
        "buy_rule": "Buy only if decision is BUY or STRONG BUY and the stock is under your budget.",
        "wait_rule": "If decision is WATCH, do not buy yet. Just track it for a few days.",
        "sell_rule": "Sell when target is reached, stop-loss is hit, or the original reason for buying becomes invalid.",
        "risk_rule": "Never put all money in one stock. Start with one small position.",
        "beginner_tip": "For now, focus only on under-Rs. 500 equity stocks and avoid options until basics become comfortable.",
    }


def get_market_overview() -> dict:
    shortlist = generate_trade_ideas(budget=500, segment="all", limit=8)
    bullish = sum(1 for item in shortlist if item["decision"] in {"STRONG BUY", "BUY"})
    watch = sum(1 for item in shortlist if item["decision"] == "WATCH")
    avg_score = round(sum(item["score"] for item in shortlist) / len(shortlist), 1) if shortlist else 0

    mood = "Neutral"
    if bullish >= 5:
        mood = "Bullish"
    elif bullish <= 2:
        mood = "Cautious"

    return {
        "market_mood": mood,
        "avg_score": avg_score,
        "bullish_count": bullish,
        "watch_count": watch,
        "top_pick": shortlist[0] if shortlist else None,
        "trade_count": len(shortlist),
        "news_api_configured": bool(NEWS_API_KEY),
    }
