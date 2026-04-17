from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from bot import analyze_symbol

DATA_FILE = Path(__file__).resolve().parent / "practice_data.json"
DEFAULT_CAPITAL = 5000.0


def _default_state() -> dict[str, Any]:
    return {
        "paper_cash": DEFAULT_CAPITAL,
        "positions": [],
        "closed_trades": [],
        "journal": [],
    }


def _load_state() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return _default_state()

    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()


def _save_state(state: dict[str, Any]) -> None:
    DATA_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _current_price(symbol: str) -> float:
    analysis = analyze_symbol(symbol.upper(), budget=500)
    return float(analysis["price"])


def _calc_position_metrics(position: dict[str, Any]) -> dict[str, Any]:
    analysis = analyze_symbol(position["symbol"], budget=500)
    current_price = float(analysis["price"])
    qty = float(position["qty"])
    avg_price = float(position["avg_price"])
    invested = round(avg_price * qty, 2)
    market_value = round(current_price * qty, 2)
    pnl = round(market_value - invested, 2)
    pnl_pct = round((pnl / invested) * 100, 2) if invested else 0.0
    stop_loss = float(position.get("stop_loss") or analysis.get("stop_loss") or avg_price * 0.97)
    target = float(position.get("target") or analysis.get("target") or avg_price * 1.05)

    alert = "HOLDING"
    alert_color = "watch"
    if current_price <= stop_loss:
        alert = "STOP LOSS HIT"
        alert_color = "avoid"
    elif current_price >= target:
        alert = "TARGET HIT"
        alert_color = "buy"

    enriched = dict(position)
    enriched.update(
        {
            "current_price": round(current_price, 2),
            "invested": invested,
            "market_value": market_value,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pnl_pct,
            "stop_loss": round(stop_loss, 2),
            "target": round(target, 2),
            "alert": alert,
            "alert_color": alert_color,
        }
    )
    return enriched


def get_practice_dashboard() -> dict[str, Any]:
    state = _load_state()
    positions = []
    total_invested = 0.0
    total_value = 0.0

    for position in state["positions"]:
        try:
            enriched = _calc_position_metrics(position)
        except Exception:
            enriched = dict(position)
            enriched.update(
                {
                    "current_price": position["avg_price"],
                    "invested": round(position["avg_price"] * position["qty"], 2),
                    "market_value": round(position["avg_price"] * position["qty"], 2),
                    "unrealized_pnl": 0.0,
                    "unrealized_pnl_pct": 0.0,
                }
            )
        positions.append(enriched)
        total_invested += enriched["invested"]
        total_value += enriched["market_value"]

    realized_pnl = round(sum(float(trade.get("pnl", 0.0)) for trade in state["closed_trades"]), 2)
    unrealized_pnl = round(total_value - total_invested, 2)
    portfolio_value = round(float(state["paper_cash"]) + total_value, 2)
    wins = sum(1 for trade in state["closed_trades"] if float(trade.get("pnl", 0.0)) > 0)
    losses = sum(1 for trade in state["closed_trades"] if float(trade.get("pnl", 0.0)) < 0)
    closed_count = len(state["closed_trades"])
    win_rate = round((wins / closed_count) * 100, 2) if closed_count else 0.0
    avg_profit = round(
        sum(float(trade.get("pnl", 0.0)) for trade in state["closed_trades"] if float(trade.get("pnl", 0.0)) > 0) / wins,
        2,
    ) if wins else 0.0
    avg_loss = round(
        sum(float(trade.get("pnl", 0.0)) for trade in state["closed_trades"] if float(trade.get("pnl", 0.0)) < 0) / losses,
        2,
    ) if losses else 0.0
    alerts = [position for position in positions if position.get("alert") in {"TARGET HIT", "STOP LOSS HIT"}]
    challenge_progress = min(closed_count, 5)

    return {
        "paper_cash": round(float(state["paper_cash"]), 2),
        "positions": positions,
        "closed_trades": state["closed_trades"][-10:][::-1],
        "journal": state["journal"][-10:][::-1],
        "alerts": alerts,
        "summary": {
            "starting_capital": DEFAULT_CAPITAL,
            "paper_cash": round(float(state["paper_cash"]), 2),
            "money_in_market": round(total_invested, 2),
            "portfolio_value": portfolio_value,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total_pnl": round(realized_pnl + unrealized_pnl, 2),
            "open_positions": len(positions),
            "closed_trades": closed_count,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "challenge_completed": closed_count >= 5,
            "challenge_progress": challenge_progress,
            "challenge_target": 5,
        },
    }


def paper_buy(symbol: str, qty: int, note: str = "") -> dict[str, Any]:
    symbol = symbol.upper()
    if qty < 1:
        return {"error": "Quantity must be at least 1"}

    state = _load_state()
    try:
        analysis = analyze_symbol(symbol.upper(), budget=500)
        price = float(analysis["price"])
    except Exception as exc:
        return {"error": f"Unable to fetch live price for {symbol}", "details": str(exc)}
    total_cost = round(price * qty, 2)

    if total_cost > float(state["paper_cash"]):
        return {"error": "Not enough paper cash for this trade"}

    state["paper_cash"] = round(float(state["paper_cash"]) - total_cost, 2)
    state["positions"].append(
        {
            "id": str(uuid4()),
            "symbol": symbol,
            "qty": qty,
            "avg_price": round(price, 2),
            "entry_value": total_cost,
            "entry_time": _now(),
            "stop_loss": analysis.get("stop_loss"),
            "target": analysis.get("target"),
            "note": note.strip(),
        }
    )
    state["journal"].append(
        {
            "id": str(uuid4()),
            "type": "BUY",
            "symbol": symbol,
            "qty": qty,
            "price": round(price, 2),
            "note": note.strip() or "Paper buy executed for learning.",
            "created_at": _now(),
        }
    )
    _save_state(state)
    return {"ok": True, "message": f"Paper bought {qty} of {symbol} at Rs. {round(price, 2)}"}


def paper_sell(position_id: str, note: str = "") -> dict[str, Any]:
    state = _load_state()
    position = next((row for row in state["positions"] if row["id"] == position_id), None)
    if not position:
        return {"error": "Practice position not found"}

    try:
        price = _current_price(position["symbol"])
    except Exception as exc:
        return {"error": f"Unable to fetch live price for {position['symbol']}", "details": str(exc)}
    qty = float(position["qty"])
    exit_value = round(price * qty, 2)
    entry_value = round(float(position["avg_price"]) * qty, 2)
    pnl = round(exit_value - entry_value, 2)
    pnl_pct = round((pnl / entry_value) * 100, 2) if entry_value else 0.0

    state["paper_cash"] = round(float(state["paper_cash"]) + exit_value, 2)
    state["positions"] = [row for row in state["positions"] if row["id"] != position_id]
    closed_trade = {
        "id": str(uuid4()),
        "symbol": position["symbol"],
        "qty": position["qty"],
        "entry_price": position["avg_price"],
        "exit_price": round(price, 2),
        "entry_time": position["entry_time"],
        "exit_time": _now(),
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "lesson": note.strip() or "Closed in practice mode.",
    }
    state["closed_trades"].append(closed_trade)
    state["journal"].append(
        {
            "id": str(uuid4()),
            "type": "SELL",
            "symbol": position["symbol"],
            "qty": position["qty"],
            "price": round(price, 2),
            "note": note.strip() or ("Booked profit." if pnl >= 0 else "Exited to control loss."),
            "created_at": _now(),
        }
    )
    _save_state(state)
    return {"ok": True, "message": f"Paper sold {position['symbol']} at Rs. {round(price, 2)}", "trade": closed_trade}


def add_journal_note(symbol: str, note: str, mood: str = "neutral") -> dict[str, Any]:
    state = _load_state()
    clean_note = note.strip()
    if not clean_note:
        return {"error": "Journal note cannot be empty"}

    entry = {
        "id": str(uuid4()),
        "type": "NOTE",
        "symbol": symbol.upper() if symbol else "GENERAL",
        "mood": mood,
        "note": clean_note,
        "created_at": _now(),
    }
    state["journal"].append(entry)
    _save_state(state)
    return {"ok": True, "entry": entry}


def reset_practice_account() -> dict[str, Any]:
    state = _default_state()
    _save_state(state)
    return {"ok": True, "message": "Practice account reset to fresh state."}
