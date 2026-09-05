"""
§9 — Regime Detection. One of the most important components: the same
signal behaves differently in different regimes.

Two layers:
  classify(df)                 -> per-symbol "trending"/"ranging"/"choppy"
                                   (original logic, still drives strategy
                                   selection in strategies.py)
  classify_market_regime(spy)  -> market-wide regime label from the doc's
                                   §9 list (TRENDING_BULL, PANIC, ...),
                                   used by signal_fusion.py to scale
                                   conviction and by the risk engine
                                   indirectly through main.py's display.
"""
import numpy as np
import pandas as pd
import config


def classify(df_with_indicators: pd.DataFrame) -> str:
    """
    Returns one of: "trending", "ranging", "choppy"

    - choppy:   current Bollinger width is in the bottom slice of its own
                recent range (unusually tight even for this symbol) -> no
                strategy has a reliable edge
    - trending: not unusually tight, and ADX above threshold -> trend-following
    - ranging:  not unusually tight, ADX below threshold -> mean-reversion
    """
    last = df_with_indicators.iloc[-1]
    adx_val = last.get("adx_14")
    bb_width = last.get("bb_width")

    if pd.isna(adx_val) or pd.isna(bb_width):
        return "choppy"

    width_history = df_with_indicators["bb_width"].dropna()
    if len(width_history) < 20:
        return "choppy"

    # What fraction of recent bars had a width <= today's width?
    # A low percentile means today is unusually tight for THIS symbol.
    percentile = (width_history <= bb_width).mean()

    if percentile <= config.CHOP_WIDTH_PERCENTILE:
        return "choppy"

    if adx_val >= config.ADX_TREND_THRESHOLD:
        return "trending"

    return "ranging"


def classify_market_regime(benchmark_df_with_indicators: "pd.DataFrame | None") -> dict:
    """Classifies the broad market using the benchmark (default SPY) as a
    breadth/trend/volatility proxy. Returns the regime label plus the raw
    readings that produced it so callers can explain themselves.

    Labels (§9): TRENDING_BULL, TRENDING_BEAR, LOW_VOL_RANGE, HIGH_VOL_RANGE,
    BREAKOUT, PANIC, RECOVERY, UNKNOWN.
    """
    if benchmark_df_with_indicators is None or benchmark_df_with_indicators.empty:
        return {"regime": "UNKNOWN", "detail": "no benchmark data available"}

    df = benchmark_df_with_indicators
    last = df.iloc[-1]
    adx_val = last.get("adx_14", np.nan)
    slope = last.get("slope_20", np.nan)
    vol_pct = last.get("vol_percentile_100", np.nan)
    ret_5 = None
    if len(df) > 5:
        ret_5 = float(df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1.0)

    trending = not pd.isna(adx_val) and adx_val >= config.ADX_TREND_THRESHOLD
    bullish = not pd.isna(slope) and slope > 0
    bearish = not pd.isna(slope) and slope < 0
    high_vol = not pd.isna(vol_pct) and vol_pct >= config.VOL_EXPANSION_PERCENTILE
    low_vol = not pd.isna(vol_pct) and vol_pct <= config.VOL_COMPRESSION_PERCENTILE

    # Panic: sharp drawdown + high volatility together.
    if ret_5 is not None and ret_5 <= -0.03 and high_vol:
        regime = "PANIC"
    # Recovery: coming off a recent sharp drawdown but now bouncing.
    elif ret_5 is not None and ret_5 >= 0.02 and not pd.isna(vol_pct) and vol_pct >= 0.5 and bullish:
        regime = "RECOVERY"
    elif trending and bullish:
        regime = "TRENDING_BULL"
    elif trending and bearish:
        regime = "TRENDING_BEAR"
    elif high_vol and not trending:
        regime = "HIGH_VOL_RANGE"
    elif low_vol and not trending:
        regime = "LOW_VOL_RANGE"
    elif ret_5 is not None and abs(ret_5) >= 0.02 and high_vol:
        regime = "BREAKOUT"
    else:
        regime = "HIGH_VOL_RANGE" if high_vol else "LOW_VOL_RANGE"

    return {
        "regime": regime,
        "benchmark_adx": None if pd.isna(adx_val) else round(float(adx_val), 1),
        "benchmark_slope_20": None if pd.isna(slope) else float(slope),
        "benchmark_vol_percentile": None if pd.isna(vol_pct) else round(float(vol_pct), 3),
        "benchmark_5bar_return_pct": None if ret_5 is None else round(ret_5 * 100, 2),
    }


# Per-regime multiplier applied to the composite score's confidence in
# signal_fusion.py — e.g. long signals get less benefit of the doubt during
# a market-wide PANIC even if the individual stock's features look fine.
REGIME_CONFIDENCE_MULTIPLIER = {
    "TRENDING_BULL": 1.10,
    "TRENDING_BEAR": 1.10,
    "LOW_VOL_RANGE": 0.90,
    "HIGH_VOL_RANGE": 0.85,
    "BREAKOUT": 1.05,
    "PANIC": 0.60,
    "RECOVERY": 0.95,
    "UNKNOWN": 1.0,
}
