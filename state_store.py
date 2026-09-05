"""
Tiny JSON-backed state store. This is the source of truth the risk engine
uses, since there's no Fidelity API to pull real account data from.
Keep it updated via trade_log.py.
"""
import json
import os
from datetime import datetime, timedelta

import config

DEFAULT_STATE = {
    "equity": 0.0,
    "peak_equity": 0.0,
    "daily_start_equity": 0.0,
    "daily_pnl": 0.0,
    "last_reset_date": None,
    "day_trade_timestamps": [],   # ISO datetimes of trades that were opened+closed same day
    "open_positions": {},         # symbol -> {"qty": int, "avg_price": float, "opened": iso}
    "trade_history": [],
}


def load() -> dict:
    if not os.path.exists(config.STATE_FILE):
        return dict(DEFAULT_STATE)
    with open(config.STATE_FILE, "r") as f:
        state = json.load(f)
    for k, v in DEFAULT_STATE.items():
        state.setdefault(k, v)
    _maybe_roll_daily(state)
    return state


def save(state: dict) -> None:
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def _maybe_roll_daily(state: dict) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("last_reset_date") != today:
        state["daily_start_equity"] = state.get("equity", 0.0)
        state["daily_pnl"] = 0.0
        state["last_reset_date"] = today
        save(state)


def set_equity(new_equity: float) -> dict:
    state = load()
    state["equity"] = new_equity
    state["peak_equity"] = max(state.get("peak_equity", 0.0), new_equity)
    state["daily_pnl"] = new_equity - state.get("daily_start_equity", new_equity)
    save(state)
    return state


def log_trade(symbol: str, side: str, qty: float, price: float, timestamp: datetime = None) -> dict:
    state = load()
    now = timestamp or datetime.now()
    entry = {
        "symbol": symbol, "side": side, "qty": qty,
        "price": price, "timestamp": now.isoformat(),
    }
    state["trade_history"].append(entry)

    pos = state["open_positions"].get(symbol)
    if side.upper() == "BUY":
        if pos:
            pos["qty"] += qty
        else:
            state["open_positions"][symbol] = {"qty": qty, "avg_price": price, "opened": now.isoformat()}
    elif side.upper() == "SELL":
        if pos:
            opened_today = datetime.fromisoformat(pos["opened"]).date() == now.date()
            if opened_today:
                state["day_trade_timestamps"].append(now.isoformat())
            pos["qty"] -= qty
            if pos["qty"] <= 0:
                del state["open_positions"][symbol]

    save(state)
    return state


def day_trade_count_last_5_sessions(state: dict) -> int:
    cutoff = datetime.now() - timedelta(days=7)  # rough proxy for "5 trading days"
    return sum(1 for ts in state.get("day_trade_timestamps", []) if datetime.fromisoformat(ts) >= cutoff)
