"""
§8 — Correlation / Pair Relationship engine.

Builds a correlation matrix across whatever symbols were fetched in the
current scan, and a simple beta-hedged spread + z-score for any pair —
the stated foundation for statistical arbitrage. This is a research/
monitoring tool (menu option), not wired into the per-symbol composite
score, since correlation structure is a portfolio-level property.
"""
import numpy as np
import pandas as pd

import config


def build_return_matrix(bars_by_symbol: dict) -> pd.DataFrame:
    """bars_by_symbol: {symbol: OHLCV DataFrame}. Returns a DataFrame of
    aligned log returns, one column per symbol, inner-joined on timestamp."""
    series = {}
    for sym, df in bars_by_symbol.items():
        if df is None or df.empty:
            continue
        series[sym] = np.log(df["Close"] / df["Close"].shift(1))
    if not series:
        return pd.DataFrame()
    return pd.concat(series, axis=1).dropna(how="any")


def correlation_matrix(bars_by_symbol: dict, lookback: int = None) -> pd.DataFrame:
    lookback = lookback or config.CORRELATION_LOOKBACK
    returns = build_return_matrix(bars_by_symbol)
    if returns.empty:
        return pd.DataFrame()
    return returns.tail(lookback).corr()


def detect_unusual_correlations(corr: pd.DataFrame, high_thresh: float = 0.9, low_thresh: float = 0.1) -> dict:
    """Flags pairs that are unusually highly correlated or have broken down
    (near-zero correlation) among names that typically move together."""
    if corr.empty:
        return {"high_correlation_pairs": [], "low_correlation_pairs": []}

    high_pairs, low_pairs = [], []
    cols = corr.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = cols[i], cols[j]
            val = corr.iloc[i, j]
            if pd.isna(val):
                continue
            if val >= high_thresh:
                high_pairs.append((a, b, round(float(val), 2)))
            elif abs(val) <= low_thresh:
                low_pairs.append((a, b, round(float(val), 2)))

    high_pairs.sort(key=lambda t: -t[2])
    low_pairs.sort(key=lambda t: abs(t[2]))
    return {"high_correlation_pairs": high_pairs[:15], "low_correlation_pairs": low_pairs[:15]}


def pair_spread_zscore(bars_by_symbol: dict, symbol_a: str, symbol_b: str, window: int = 60):
    """Spread = A - beta*B, beta estimated by OLS on log prices over the
    window; returns the current z-score of that spread (§8 example)."""
    if symbol_a not in bars_by_symbol or symbol_b not in bars_by_symbol:
        return None
    a = np.log(bars_by_symbol[symbol_a]["Close"]).tail(window)
    b = np.log(bars_by_symbol[symbol_b]["Close"]).tail(window)
    joined = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
    if len(joined) < 10:
        return None

    beta = np.polyfit(joined["b"], joined["a"], 1)[0]
    spread = joined["a"] - beta * joined["b"]
    z = (spread.iloc[-1] - spread.mean()) / spread.std() if spread.std() else np.nan
    if pd.isna(z):
        return None
    return {"symbol_a": symbol_a, "symbol_b": symbol_b, "beta": round(float(beta), 3),
            "spread_zscore": round(float(z), 2)}
