"""
Execution layer — runs AFTER signal_fusion.py has already decided the
direction (BUY/SELL/HOLD) from the full multi-engine composite score. This
module's only job is: given a side, turn it into concrete ATR-based
entry/stop/target levels, and label which "style" of setup it most
resembles so the notifier can explain the trade in plain English.

This replaces the old regime -> {trend_following, mean_reversion} branch:
regime is now one input among many into the composite score (see
signal_fusion.py / regime.py) rather than a hard switch that decides which
single strategy gets to vote.
"""
import config


def _levels(entry: float, atr_val: float, side: str):
    if side == "BUY":
        stop = entry - config.ATR_STOP_MULTIPLIER * atr_val
        target = entry + config.ATR_TARGET_MULTIPLIER * atr_val
    elif side == "SELL":
        stop = entry + config.ATR_STOP_MULTIPLIER * atr_val
        target = entry - config.ATR_TARGET_MULTIPLIER * atr_val
    else:
        stop = target = None
    return stop, target


def dominant_style(contributions: dict) -> str:
    """Labels the setup by whichever engine contributed the most to the
    composite score, purely for the human-readable explanation — it does
    not change the entry/stop/target math."""
    if not contributions:
        return "fusion"
    top = max(contributions.items(), key=lambda kv: abs(kv[1]))[0]
    style_map = {
        "trend": "trend_following",
        "momentum": "trend_following",
        "mean_reversion": "mean_reversion",
        "structure": "breakout_structure",
        "relative_strength": "relative_strength",
        "volume": "volume_driven",
        "ml": "ml_model",
    }
    return style_map.get(top, "fusion")


def compute_levels(df, side: str) -> dict:
    last = df.iloc[-1]
    entry = float(last["Close"])
    atr_val = float(last["atr_14"]) if last.get("atr_14") == last.get("atr_14") else None  # NaN-safe

    if atr_val is None or atr_val <= 0:
        return {"entry": entry, "stop": None, "target": None, "atr": atr_val}

    stop, target = _levels(entry, atr_val, side)
    return {
        "entry": round(entry, 2),
        "stop": round(stop, 2) if stop is not None else None,
        "target": round(target, 2) if target is not None else None,
        "atr": round(atr_val, 4),
    }
