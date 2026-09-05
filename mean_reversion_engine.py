"""
§3 — Mean-reversion engine.

Z-score of price vs its own rolling mean/std. The score is DAMPENED (not
zeroed) when a strong trend is present, per the doc's explicit warning that
"a stock can remain +3 sigma from its mean while continuing to trend" — so
this is one vote among several in signal_fusion.py, never an automatic
short-the-top / buy-the-dip trigger on its own.
"""
import numpy as np
import pandas as pd

import indicators


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute(df: pd.DataFrame, window: int = 20, trend_strength: float = 0.0) -> dict:
    z_series = indicators.zscore(df["Close"], window)
    z = z_series.iloc[-1]

    if pd.isna(z):
        return {"zscore": None, "mean_reversion_score": 0.0, "classification": "insufficient_data"}

    z = float(z)
    if z >= 3.0:
        classification = "extreme_stretched_high"
    elif z >= 2.0:
        classification = "stretched_high"
    elif z <= -3.0:
        classification = "extreme_stretched_low"
    elif z <= -2.0:
        classification = "stretched_low"
    else:
        classification = "normal_range"

    # Raw contrarian score: negative z (oversold) -> positive (long) vote.
    raw_score = _clip(-z / 3.0)

    # Dampen the contrarian vote in proportion to how strong the prevailing
    # trend is — a trending stock is allowed to stay stretched.
    damp = 1.0 - _clip(abs(trend_strength), 0.0, 1.0) * 0.7
    mean_reversion_score = round(raw_score * damp, 3)

    return {
        "zscore": round(z, 2),
        "classification": classification,
        "mean_reversion_score": mean_reversion_score,
    }
