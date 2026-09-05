"""
§4 — Volatility engine.

Volatility is directionless by itself (it doesn't vote long or short) but
it materially changes how much weight other signals deserve: a breakout
during a volatility expansion off a compression is far more informative
than the same price move during already-elevated, directionless volatility.
`vol_confidence_multiplier` is what signal_fusion.py uses to scale the
composite score.
"""
import numpy as np
import pandas as pd

import config


def compute(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]

    realized = last.get("realized_vol_20", np.nan)
    parkinson = last.get("parkinson_vol_20", np.nan)
    gk = last.get("gk_vol_20", np.nan)
    yz = last.get("yz_vol_20", np.nan)
    percentile = last.get("vol_percentile_100", np.nan)
    atr_val = last.get("atr_14", np.nan)

    state = "unknown"
    if not pd.isna(percentile):
        if percentile <= config.VOL_COMPRESSION_PERCENTILE:
            state = "compression"
        elif percentile >= config.VOL_EXPANSION_PERCENTILE:
            state = "expansion"
        else:
            state = "normal"

    # Was today's bar range itself a big expansion vs recent ATR? Cheap,
    # bar-level companion to the rolling-percentile view above.
    bar_range = last["High"] - last["Low"]
    range_vs_atr = float(bar_range / atr_val) if atr_val and not pd.isna(atr_val) and atr_val > 0 else None

    # Confidence multiplier: compression -> lower conviction (nothing has
    # confirmed direction yet, "watch for expansion" per the doc); a fresh
    # expansion off a prior compression -> higher conviction; already-high,
    # non-expanding vol -> lower conviction (chop / noise risk).
    if state == "compression":
        multiplier = 0.7
    elif state == "expansion":
        multiplier = 1.15
    elif state == "normal":
        multiplier = 1.0
    else:
        multiplier = 1.0

    return {
        "realized_vol_20": None if pd.isna(realized) else round(float(realized), 4),
        "parkinson_vol_20": None if pd.isna(parkinson) else round(float(parkinson), 4),
        "gk_vol_20": None if pd.isna(gk) else round(float(gk), 4),
        "yz_vol_20": None if pd.isna(yz) else round(float(yz), 4),
        "vol_percentile": None if pd.isna(percentile) else round(float(percentile), 3),
        "vol_state": state,
        "range_vs_atr": None if range_vs_atr is None else round(range_vs_atr, 2),
        "vol_confidence_multiplier": multiplier,
        # a bounded, sign-free "volatility score" purely for the composite
        # display in §14/§18 — reflects conviction, not direction.
        "volatility_score": round(min(1.0, multiplier - 0.5), 3),
    }
