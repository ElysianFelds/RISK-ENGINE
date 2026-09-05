"""
§16 — Event / Anomaly engine.

Separate from directional signal fusion on purpose: an anomaly alert says
"pay attention here", not "buy" or "sell". Useful standalone when scanning
a large watchlist for outliers.
"""
import numpy as np
import pandas as pd

import config


def _zscore_of_last(series: pd.Series, window: int = 60) -> float:
    tail = series.tail(window).dropna()
    if len(tail) < 10:
        return np.nan
    mean, std = tail.mean(), tail.std()
    if not std:
        return np.nan
    return float((tail.iloc[-1] - mean) / std)


def compute(df: pd.DataFrame, relative_strength_pct: float = None) -> dict:
    ret_z = _zscore_of_last(df["Close"].pct_change())
    range_z = _zscore_of_last((df["High"] - df["Low"]) / df["Close"])

    vol_z = np.nan
    if "Volume" in df.columns and df["Volume"].fillna(0).sum() > 0:
        vol_z = _zscore_of_last(df["Volume"])

    realized_vol = df.get("realized_vol_20")
    vol_of_vol_z = _zscore_of_last(realized_vol) if realized_vol is not None else np.nan

    flags = []
    threshold = config.ANOMALY_ZSCORE_THRESHOLD
    if not np.isnan(ret_z) and abs(ret_z) >= threshold:
        flags.append(f"price return {ret_z:+.1f}sigma")
    if not np.isnan(range_z) and range_z >= threshold:
        flags.append(f"bar range {range_z:+.1f}sigma")
    if not np.isnan(vol_z) and vol_z >= threshold:
        flags.append(f"volume {vol_z:+.1f}sigma")
    if not np.isnan(vol_of_vol_z) and vol_of_vol_z >= threshold:
        flags.append(f"volatility {vol_of_vol_z:+.1f}sigma")
    if relative_strength_pct is not None and abs(relative_strength_pct) >= config.ANOMALY_RS_PCT_THRESHOLD:
        flags.append(f"relative strength {relative_strength_pct:+.1f}%")

    return {
        "return_zscore": None if np.isnan(ret_z) else round(ret_z, 2),
        "range_zscore": None if np.isnan(range_z) else round(range_z, 2),
        "volume_zscore": None if np.isnan(vol_z) else round(vol_z, 2),
        "volatility_zscore": None if np.isnan(vol_of_vol_z) else round(vol_of_vol_z, 2),
        "is_anomaly": len(flags) > 0,
        "anomaly_flags": flags,
    }
