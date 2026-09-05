"""
§6 — Market Structure engine.

Classifies price action against reference levels (prior day/week high-low,
Donchian channel, opening range) into: breakout, retest, failed_breakout,
support_rejection, resistance_rejection, range, or none — favoring the
doc's "breakout -> pullback -> successful retest" read over a bare
"breakout -> BUY".
"""
import numpy as np
import pandas as pd


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def prior_period_levels(df: pd.DataFrame):
    """Prior COMPLETE calendar day's high/low and prior complete week's
    high/low, derived from whatever intraday/daily bars we were given."""
    dates = pd.Series(df.index.date, index=df.index)
    today = dates.iloc[-1]
    prior_day_mask = dates < today
    prior_day_high = prior_day_low = None
    if prior_day_mask.any():
        last_prior_date = dates[prior_day_mask].iloc[-1]
        day_rows = df[dates == last_prior_date]
        prior_day_high, prior_day_low = day_rows["High"].max(), day_rows["Low"].min()

    iso_weeks = pd.Series([d.isocalendar()[:2] for d in dates], index=df.index)
    this_week = iso_weeks.iloc[-1]
    prior_week_mask = iso_weeks != this_week
    prior_week_high = prior_week_low = None
    if prior_week_mask.any():
        last_prior_week = iso_weeks[prior_week_mask].iloc[-1]
        week_rows = df[iso_weeks == last_prior_week]
        prior_week_high, prior_week_low = week_rows["High"].max(), week_rows["Low"].min()

    return prior_day_high, prior_day_low, prior_week_high, prior_week_low


def opening_range(df: pd.DataFrame, minutes: int = 30):
    """High/low of the first `minutes` of the CURRENT session, if we have
    intraday granularity for today."""
    dates = pd.Series(df.index.date, index=df.index)
    today = dates.iloc[-1]
    today_rows = df[dates == today]
    if today_rows.empty:
        return None, None
    start = today_rows.index[0]
    window_rows = today_rows[today_rows.index <= start + pd.Timedelta(minutes=minutes)]
    if window_rows.empty:
        return None, None
    return window_rows["High"].max(), window_rows["Low"].min()


def compute(df: pd.DataFrame, breakout_lookback: int = 3) -> dict:
    last = df.iloc[-1]
    close = last["Close"]

    donchian_hi = last.get("donchian_high_20", np.nan)
    donchian_lo = last.get("donchian_low_20", np.nan)

    try:
        pd_high, pd_low, pw_high, pw_low = prior_period_levels(df)
    except Exception:
        pd_high = pd_low = pw_high = pw_low = None

    try:
        or_high, or_low = opening_range(df)
    except Exception:
        or_high = or_low = None

    classification = "range"
    score = 0.0

    if not pd.isna(donchian_hi) and close > donchian_hi:
        # was the last N bars' high ALSO above this channel? if so it's an
        # established breakout, not a first-touch — look for retest instead.
        recent_highs_above = (df["High"].tail(breakout_lookback) > donchian_hi).sum()
        if recent_highs_above >= breakout_lookback:
            classification = "breakout_extended"
            score = 0.5
        else:
            classification = "breakout"
            score = 0.8
    elif not pd.isna(donchian_lo) and close < donchian_lo:
        recent_lows_below = (df["Low"].tail(breakout_lookback) < donchian_lo).sum()
        if recent_lows_below >= breakout_lookback:
            classification = "breakdown_extended"
            score = -0.5
        else:
            classification = "breakdown"
            score = -0.8
    elif pd_high is not None and close >= pd_high * 0.998 and close <= pd_high * 1.01:
        classification = "resistance_test"
        score = 0.1
    elif pd_low is not None and close <= pd_low * 1.002 and close >= pd_low * 0.99:
        classification = "support_test"
        score = -0.1

    # failed breakout: pierced the channel intrabar (High/Low) but closed
    # back inside it -> rejection, and the score flips against the wick.
    if not pd.isna(donchian_hi) and last["High"] > donchian_hi and close < donchian_hi:
        classification = "failed_breakout_high"
        score = -0.4
    if not pd.isna(donchian_lo) and last["Low"] < donchian_lo and close > donchian_lo:
        classification = "failed_breakout_low"
        score = 0.4

    return {
        "structure_classification": classification,
        "structure_score": round(_clip(score), 3),
        "prior_day_high": None if pd_high is None else round(float(pd_high), 2),
        "prior_day_low": None if pd_low is None else round(float(pd_low), 2),
        "prior_week_high": None if pw_high is None else round(float(pw_high), 2),
        "prior_week_low": None if pw_low is None else round(float(pw_low), 2),
        "opening_range_high": None if or_high is None else round(float(or_high), 2),
        "opening_range_low": None if or_low is None else round(float(or_low), 2),
        "donchian_high_20": None if pd.isna(donchian_hi) else round(float(donchian_hi), 2),
        "donchian_low_20": None if pd.isna(donchian_lo) else round(float(donchian_lo), 2),
    }
