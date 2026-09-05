"""
§10 — Multi-timeframe engine.

Full 1m/5m/15m/1h/4h/1D/1W cascade would multiply API calls per symbol per
scan; as a practical foundation this module adds ONE higher timeframe
(daily, via yfinance so no extra key/rate-limit is consumed) alongside
whatever intraday timeframe main.py already fetched, and scores whether
they agree. Extending HIGHER_TIMEFRAMES below is the natural next step if
a paid data plan makes more calls affordable.
"""
import numpy as np
import pandas as pd

import indicators

_daily_cache: dict = {}  # symbol -> (fetched_at, DataFrame) — avoid refetching every scan


def _trend_direction(df_with_indicators: pd.DataFrame) -> float:
    """+1 bullish, -1 bearish, 0 unclear, from EMA9/21 + price vs SMA50."""
    last = df_with_indicators.iloc[-1]
    votes = []
    if not pd.isna(last.get("ema_9")) and not pd.isna(last.get("ema_21")):
        votes.append(1.0 if last["ema_9"] > last["ema_21"] else -1.0)
    if not pd.isna(last.get("Close")) and not pd.isna(last.get("sma_50")):
        votes.append(1.0 if last["Close"] > last["sma_50"] else -1.0)
    return float(np.mean(votes)) if votes else 0.0


def get_daily_bars(symbol: str, cache_minutes: int = 55) -> "pd.DataFrame | None":
    import time
    now = time.time()
    cached = _daily_cache.get(symbol)
    if cached and now - cached[0] < cache_minutes * 60:
        return cached[1]

    try:
        import yfinance as yf
        df = yf.download(symbol, period="1y", interval="1d", progress=False, auto_adjust=True, timeout=10)
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        _daily_cache[symbol] = (now, df)
        return df
    except Exception:
        return None


def compute(symbol: str, intraday_df_with_indicators: pd.DataFrame, weights: dict = None) -> dict:
    weights = weights or {"daily": 0.6, "intraday": 0.4}

    intraday_dir = _trend_direction(intraday_df_with_indicators)

    daily_raw = get_daily_bars(symbol)
    daily_dir = 0.0
    daily_available = False
    if daily_raw is not None and len(daily_raw) >= 55:
        daily_with_ind = indicators.compute_all(daily_raw)
        daily_dir = _trend_direction(daily_with_ind)
        daily_available = True

    if daily_available:
        alignment_score = weights["daily"] * daily_dir + weights["intraday"] * intraday_dir
    else:
        alignment_score = intraday_dir

    agreement = daily_available and (daily_dir * intraday_dir > 0)

    return {
        "daily_trend": "bullish" if daily_dir > 0 else ("bearish" if daily_dir < 0 else "neutral"),
        "intraday_trend": "bullish" if intraday_dir > 0 else ("bearish" if intraday_dir < 0 else "neutral"),
        "timeframes_agree": bool(agreement),
        "trend_alignment_score": round(float(max(-1.0, min(1.0, alignment_score))), 3),
        "daily_data_available": daily_available,
    }
