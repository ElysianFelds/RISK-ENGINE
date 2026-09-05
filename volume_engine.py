"""
§5 — Volume / Liquidity engine.

If the data source didn't provide real volume (some free intraday feeds
zero it out), every field here degrades to None/neutral rather than
fabricating a signal.
"""
import numpy as np
import pandas as pd

import config


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def has_volume(df: pd.DataFrame) -> bool:
    return "Volume" in df.columns and df["Volume"].fillna(0).tail(20).sum() > 0


def compute(df: pd.DataFrame) -> dict:
    if not has_volume(df):
        return {
            "rvol": None, "vwap_dist_pct": None, "obv_slope": None,
            "price_volume_divergence": False, "volume_score": 0.0,
            "note": "no real volume data from this provider",
        }

    last = df.iloc[-1]
    rvol = last.get("rvol_20", np.nan)
    vwap_dist = last.get("vwap_dist_pct", np.nan)

    obv_tail = df["obv"].tail(10).dropna()
    obv_slope = float(obv_tail.iloc[-1] - obv_tail.iloc[0]) if len(obv_tail) >= 2 else None

    price_up = df["Close"].iloc[-1] > df["Close"].iloc[-5] if len(df) >= 5 else None
    obv_up = obv_slope is not None and obv_slope > 0
    divergence = (price_up is True and obv_up is False) or (price_up is False and obv_up is True)

    rvol_component = 0.0
    if not pd.isna(rvol):
        rvol_component = _clip((float(rvol) - 1.0) / config.RVOL_STRONG_THRESHOLD)

    price_dir = 1.0 if (price_up is True) else (-1.0 if price_up is False else 0.0)
    volume_score = _clip(price_dir * max(0.0, rvol_component))
    if divergence:
        volume_score *= 0.4  # divergence undercuts conviction in the move

    return {
        "rvol": None if pd.isna(rvol) else round(float(rvol), 2),
        "vwap_dist_pct": None if pd.isna(vwap_dist) else round(float(vwap_dist) * 100, 2),
        "obv_slope": obv_slope,
        "price_volume_divergence": bool(divergence),
        "volume_score": round(volume_score, 3),
    }
