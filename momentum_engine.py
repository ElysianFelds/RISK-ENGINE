"""
§2 — Momentum & Trend engine.

Produces two scores in [-1, +1]:
  trend_score    : is there a clean, confirmed directional trend right now?
  momentum_score : has price actually been moving, adjusted for volatility?

Both feed signal_fusion.py as independent votes rather than being collapsed
into one number, since a market can have strong momentum without a clean
trend (choppy-but-moving) or vice versa.
"""
import numpy as np
import pandas as pd

import config

HORIZONS = (1, 3, 5, 10, 20, 60, 120, 252)


def multi_horizon_momentum(df: pd.DataFrame) -> dict:
    """M_h = ln(P_t / P_(t-h)) / sigma_h  — volatility-normalized return over
    each horizon (§2). Horizons longer than the available history are
    skipped rather than padded with garbage."""
    close = df["Close"]
    out = {}
    for h in HORIZONS:
        if len(close) <= h + 5:
            continue
        raw_ret = np.log(close.iloc[-1] / close.iloc[-1 - h])
        window_rets = np.log(close / close.shift(1)).tail(max(h, 20))
        sigma = window_rets.std()
        out[f"M{h}"] = float(raw_ret / sigma) if sigma and not np.isnan(sigma) and sigma > 0 else 0.0
    return out


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute(df: pd.DataFrame) -> dict:
    last, prev = df.iloc[-1], df.iloc[-2]

    m = multi_horizon_momentum(df)
    # blend a short and a medium horizon so a single noisy print can't flip the score
    short_term = m.get("M5", m.get("M3", 0.0))
    medium_term = m.get("M20", m.get("M10", short_term))
    momentum_raw = 0.5 * short_term + 0.5 * medium_term
    momentum_score = _clip(momentum_raw / 2.5)  # 2.5 vol-adjusted units ~= saturating move

    ema_cross_up = prev["ema_9"] <= prev["ema_21"] and last["ema_9"] > last["ema_21"]
    ema_cross_down = prev["ema_9"] >= prev["ema_21"] and last["ema_9"] < last["ema_21"]
    above_trend = bool(last["Close"] > last["sma_50"]) if not pd.isna(last["sma_50"]) else False
    below_trend = bool(last["Close"] < last["sma_50"]) if not pd.isna(last["sma_50"]) else False

    adx_val = last.get("adx_14", np.nan)
    slope = last.get("slope_20", np.nan)
    r2 = last.get("r2_20", np.nan)
    donchian_hi = last.get("donchian_high_20", np.nan)
    donchian_lo = last.get("donchian_low_20", np.nan)

    donchian_breakout_up = not pd.isna(donchian_hi) and last["Close"] > donchian_hi
    donchian_breakout_down = not pd.isna(donchian_lo) and last["Close"] < donchian_lo

    trend_dir = 0.0
    if not pd.isna(slope):
        trend_dir = 1.0 if slope > 0 else (-1.0 if slope < 0 else 0.0)

    trend_strength = 0.0
    if not pd.isna(adx_val):
        trend_strength = _clip((adx_val - config.ADX_TREND_THRESHOLD) / 30.0, 0.0, 1.0)
    r2_factor = float(r2) if not pd.isna(r2) else 0.0
    trend_score = _clip(trend_dir * trend_strength * (0.5 + 0.5 * max(0.0, r2_factor)))

    if above_trend and (ema_cross_up or trend_dir > 0):
        trend_score = max(trend_score, 0.2)
    if below_trend and (ema_cross_down or trend_dir < 0):
        trend_score = min(trend_score, -0.2)

    return {
        "momentum_horizons": m,
        "momentum_score": round(momentum_score, 3),
        "trend_score": round(trend_score, 3),
        "ema_cross_up": bool(ema_cross_up),
        "ema_cross_down": bool(ema_cross_down),
        "above_trend": above_trend,
        "below_trend": below_trend,
        "adx": None if pd.isna(adx_val) else round(float(adx_val), 1),
        "slope_20": None if pd.isna(slope) else float(slope),
        "r2_20": None if pd.isna(r2) else round(float(r2), 3),
        "donchian_breakout_up": bool(donchian_breakout_up),
        "donchian_breakout_down": bool(donchian_breakout_down),
    }
