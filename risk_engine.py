"""
Fidelity-appropriate risk engine. This is NOT a prop-firm rule set — no
trailing drawdown, no profit-consistency clause. It's the retail-account
rules that actually apply to a self-directed Fidelity account, evaluated
against the state you maintain in state.json (via trade_log.py).

Every signal passes through evaluate() and comes back stamped
APPROVED or BLOCKED: <reason>, plus a suggested share quantity.
"""
import config
import state_store


def evaluate(symbol: str, side: str, entry: float, stop: float) -> dict:
    state = state_store.load()
    equity = state.get("equity", 0.0)

    result = {"status": "APPROVED", "reason": "", "suggested_qty": 0}

    if side == "HOLD":
        result["reason"] = "No trade signal generated"
        return result

    if equity <= 0:
        result["status"] = "BLOCKED"
        result["reason"] = "Account equity not set — run `python trade_log.py set-equity <amount>` first"
        return result

    # 1. Max daily loss
    daily_pnl_pct = state.get("daily_pnl", 0.0) / equity if equity else 0
    if daily_pnl_pct <= -config.MAX_DAILY_LOSS_PCT:
        result["status"] = "BLOCKED"
        result["reason"] = (f"Max daily loss hit ({daily_pnl_pct:.1%} <= "
                             f"-{config.MAX_DAILY_LOSS_PCT:.0%}) — no new trades today")
        return result

    # 2. Max drawdown from peak
    peak = state.get("peak_equity", equity) or equity
    drawdown_pct = (equity - peak) / peak if peak else 0
    if drawdown_pct <= -config.MAX_DRAWDOWN_FROM_PEAK_PCT:
        result["status"] = "BLOCKED"
        result["reason"] = (f"Drawdown from peak equity is {drawdown_pct:.1%}, past the "
                             f"-{config.MAX_DRAWDOWN_FROM_PEAK_PCT:.0%} pause threshold")
        return result

    # 3. PDT rule (margin accounts only, equity under threshold)
    if config.ACCOUNT_TYPE == "margin" and equity < config.PDT_THRESHOLD:
        day_trades = state_store.day_trade_count_last_5_sessions(state)
        if day_trades >= config.PDT_MAX_DAY_TRADES_PER_5_DAYS:
            result["status"] = "BLOCKED"
            result["reason"] = (f"PDT limit: {day_trades} day trades already logged in the "
                                 f"rolling window and equity (${equity:,.0f}) is under "
                                 f"${config.PDT_THRESHOLD:,.0f} — opening+closing this same day "
                                 f"risks a PDT flag")
            return result
    elif config.ACCOUNT_TYPE == "cash":
        result.setdefault("notes", []).append(
            "Cash account: watch trade settlement (T+1) — reusing unsettled proceeds "
            "same-day risks a good-faith violation."
        )

    # 4. Max open positions
    open_positions = state.get("open_positions", {})
    if side == "BUY" and symbol not in open_positions and len(open_positions) >= config.MAX_OPEN_POSITIONS:
        result["status"] = "BLOCKED"
        result["reason"] = f"Already at max open positions ({config.MAX_OPEN_POSITIONS})"
        return result

    # 5. Position sizing (risk % of equity / stop distance), then concentration cap
    if stop is None:
        result["status"] = "BLOCKED"
        result["reason"] = "No stop level available to size the position safely"
        return result

    risk_dollars = equity * config.RISK_PER_TRADE_PCT
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        result["status"] = "BLOCKED"
        result["reason"] = "Stop distance is zero — cannot size position"
        return result

    qty_by_risk = int(risk_dollars / stop_distance)
    max_dollars_by_concentration = equity * config.MAX_POSITION_CONCENTRATION_PCT
    qty_by_concentration = int(max_dollars_by_concentration / entry) if entry else 0
    suggested_qty = max(0, min(qty_by_risk, qty_by_concentration))

    if suggested_qty <= 0:
        result["status"] = "BLOCKED"
        result["reason"] = (f"Sized quantity is 0 given ${risk_dollars:.2f} risk budget and "
                             f"${stop_distance:.2f} stop distance — position too small to size sensibly")
        return result

    result["suggested_qty"] = suggested_qty
    result["reason"] = (f"Risking ${risk_dollars:.2f} ({config.RISK_PER_TRADE_PCT:.0%} of "
                         f"${equity:,.0f}) at ${stop_distance:.2f}/share stop distance")
    return result
