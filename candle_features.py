"""
§1 / §11 — Candle Engine & Candle Pattern Research Engine.

Deliberately does NOT hardcode "bullish engulfing = BUY". It only *labels*
the current candle's shape and the recent swing structure. Whether a given
label actually has positive conditional forward returns is an empirical
question answered by pattern_db.py / statistics_engine.py, not by this file.
"""
import numpy as np
import pandas as pd


def classify_candle(df: pd.DataFrame, i: int = -1) -> str:
    """Returns a single descriptive label for the candle at position i,
    using only that bar and (where needed) the one before it."""
    if len(df) < 2:
        return "insufficient_data"

    last = df.iloc[i]
    prev = df.iloc[i - 1]

    body = abs(last["Close"] - last["Open"])
    rng = last["High"] - last["Low"]
    if rng == 0 or np.isnan(rng):
        return "zero_range"

    body_pct = body / rng
    is_bull = last["Close"] > last["Open"]
    is_bear = last["Close"] < last["Open"]

    # inside / outside bar relative to previous bar
    if last["High"] <= prev["High"] and last["Low"] >= prev["Low"]:
        return "inside_bar"
    if last["High"] >= prev["High"] and last["Low"] <= prev["Low"]:
        return "outside_bar_bull" if is_bull else "outside_bar_bear"

    # engulfing
    prev_body_low = min(prev["Open"], prev["Close"])
    prev_body_high = max(prev["Open"], prev["Close"])
    if is_bull and last["Open"] <= prev_body_low and last["Close"] >= prev_body_high:
        return "bullish_engulfing"
    if is_bear and last["Open"] >= prev_body_high and last["Close"] <= prev_body_low:
        return "bearish_engulfing"

    # doji / indecision
    if body_pct < 0.1:
        return "doji"

    # marubozu (near full-body candle, negligible wicks)
    if body_pct > 0.9:
        return "marubozu_bull" if is_bull else "marubozu_bear"

    # hammer / shooting star (small body, long single wick)
    upper_wick = last["High"] - max(last["Open"], last["Close"])
    lower_wick = min(last["Open"], last["Close"]) - last["Low"]
    if lower_wick > 2 * body and upper_wick < body:
        return "hammer"
    if upper_wick > 2 * body and lower_wick < body:
        return "shooting_star"

    return "bull_candle" if is_bull else "bear_candle"


def swing_structure(df: pd.DataFrame, lookback: int = 5, window: int = 60) -> str:
    """Classifies recent price structure as one of:
    higher_highs_higher_lows, lower_highs_lower_lows, mixed/range.
    Uses simple local pivots (a bar is a swing high/low if it's the max/min
    within +/- lookback bars) over the trailing `window` bars (§1)."""
    sub = df.tail(window)
    highs, lows = sub["High"].values, sub["Low"].values
    n = len(sub)
    swing_highs, swing_lows = [], []

    for i in range(lookback, n - lookback):
        window_h = highs[i - lookback:i + lookback + 1]
        window_l = lows[i - lookback:i + lookback + 1]
        if highs[i] == window_h.max():
            swing_highs.append(highs[i])
        if lows[i] == window_l.min():
            swing_lows.append(lows[i])

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "insufficient_data"

    hh = swing_highs[-1] > swing_highs[-2]
    hl = swing_lows[-1] > swing_lows[-2]
    lh = swing_highs[-1] < swing_highs[-2]
    ll = swing_lows[-1] < swing_lows[-2]

    if hh and hl:
        return "higher_highs_higher_lows"
    if lh and ll:
        return "lower_highs_lower_lows"
    return "mixed_range"


def consecutive_run(df: pd.DataFrame) -> int:
    """Positive N = N consecutive up-closes ending at the last bar,
    negative N = N consecutive down-closes."""
    closes = df["Close"].values
    if len(closes) < 2:
        return 0
    direction = np.sign(np.diff(closes))
    if direction[-1] == 0:
        return 0
    run = 1
    sign = direction[-1]
    for d in direction[-2::-1]:
        if d == sign:
            run += 1
        else:
            break
    return int(run * sign)


def compute(df: pd.DataFrame) -> dict:
    return {
        "pattern": classify_candle(df),
        "swing_structure": swing_structure(df),
        "consecutive_run": consecutive_run(df),
    }
