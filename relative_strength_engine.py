"""
§7 — Relative Strength / Cross-Sectional engine.

Never scores a stock in isolation: computes its return relative to a
benchmark (default SPY, configurable per-symbol sector ETF in
config.SECTOR_ETF_MAP) over several horizons and turns the blended result
into a bounded score.
"""
import numpy as np
import pandas as pd

import config


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _pct_return(close: pd.Series, bars: int) -> float:
    if len(close) <= bars:
        return np.nan
    return float(close.iloc[-1] / close.iloc[-1 - bars] - 1.0)


def compute(df: pd.DataFrame, benchmark_df: "pd.DataFrame | None", horizons=(5, 20, 60)) -> dict:
    if benchmark_df is None or benchmark_df.empty:
        return {
            "relative_strength_score": 0.0,
            "note": "no benchmark data available this scan",
            "per_horizon": {},
        }

    per_horizon = {}
    weighted_sum, weight_total = 0.0, 0.0
    weights = {5: 0.5, 20: 0.3, 60: 0.2}

    for h in horizons:
        stock_ret = _pct_return(df["Close"], h)
        bench_ret = _pct_return(benchmark_df["Close"], h)
        if np.isnan(stock_ret) or np.isnan(bench_ret):
            continue
        rs = stock_ret - bench_ret
        per_horizon[f"RS_{h}"] = {
            "stock_return_pct": round(stock_ret * 100, 2),
            "benchmark_return_pct": round(bench_ret * 100, 2),
            "relative_strength_pct": round(rs * 100, 2),
        }
        w = weights.get(h, 1.0 / len(horizons))
        weighted_sum += w * rs
        weight_total += w

    if weight_total == 0:
        return {"relative_strength_score": 0.0, "note": "insufficient overlapping history", "per_horizon": {}}

    blended_rs_pct = (weighted_sum / weight_total) * 100
    # +/-3% blended relative outperformance saturates the score
    score = _clip(blended_rs_pct / 3.0)

    return {
        "relative_strength_score": round(score, 3),
        "blended_relative_strength_pct": round(blended_rs_pct, 2),
        "per_horizon": per_horizon,
    }
