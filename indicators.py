"""
Technical indicators computed with plain pandas/numpy (no extra deps).

This module is the low-level feature library shared by every higher-level
engine (momentum, volatility, volume, structure, mean-reversion, ...). It
only computes numbers — it never decides BUY/SELL. Section references below
point back to quant_stock_signal_engine.md.
"""
import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


# --------------------------------------------------------------------------- moving averages / oscillators (original set)

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0):
    mid = sma(series, window)
    std = series.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower) / mid
    return upper, mid, lower, width


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    return pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)


def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr_series = atr(df, window)

    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / window, adjust=False).mean() / atr_series
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / window, adjust=False).mean() / atr_series

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.ewm(alpha=1 / window, adjust=False).mean()


# --------------------------------------------------------------------------- §2 momentum / trend building blocks

def log_returns(series: pd.Series, periods: int = 1) -> pd.Series:
    return np.log(series / series.shift(periods))


def regression_slope_r2(series: pd.Series, window: int) -> "tuple[pd.Series, pd.Series]":
    """Rolling OLS slope (price units per bar) and R² of price vs time over
    `window` bars. Distinguishes a clean trend from a noisy one with a
    similar net move (§2 Trend Features)."""
    x = np.arange(window)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()

    def _slope(y):
        if np.isnan(y).any():
            return np.nan
        return ((x - x_mean) * (y - y.mean())).sum() / x_var

    def _r2(y):
        if np.isnan(y).any():
            return np.nan
        slope = _slope(y)
        intercept = y.mean() - slope * x_mean
        pred = slope * x + intercept
        ss_res = ((y - pred) ** 2).sum()
        ss_tot = ((y - y.mean()) ** 2).sum()
        return 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

    slope = series.rolling(window).apply(_slope, raw=True)
    r2 = series.rolling(window).apply(_r2, raw=True)
    return slope, r2


def donchian(df: pd.DataFrame, window: int = 20):
    """Highest-high / lowest-low channel over `window` bars, EXCLUDING the
    current bar, so 'breakout' means the current bar exceeded the prior
    channel rather than trivially matching itself (§6 Market Structure)."""
    highest = df["High"].shift(1).rolling(window).max()
    lowest = df["Low"].shift(1).rolling(window).min()
    return highest, lowest


def zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window).mean()
    std = series.rolling(window).std()
    return (series - mean) / std.replace(0, np.nan)


# --------------------------------------------------------------------------- §4 volatility estimators

def realized_volatility(close: pd.Series, window: int = 20, annualize: bool = True) -> pd.Series:
    """Close-to-close realized volatility (std of log returns)."""
    ret = log_returns(close)
    vol = ret.rolling(window).std()
    if annualize:
        vol = vol * np.sqrt(TRADING_DAYS_PER_YEAR)
    return vol


def parkinson_volatility(df: pd.DataFrame, window: int = 20, annualize: bool = True) -> pd.Series:
    """Uses the high-low range; more efficient than close-to-close but blind
    to overnight gaps."""
    hl = np.log(df["High"] / df["Low"]) ** 2
    factor = 1.0 / (4.0 * np.log(2.0))
    var = factor * hl.rolling(window).mean()
    vol = np.sqrt(var)
    if annualize:
        vol = vol * np.sqrt(TRADING_DAYS_PER_YEAR)
    return vol


def garman_klass_volatility(df: pd.DataFrame, window: int = 20, annualize: bool = True) -> pd.Series:
    """Uses O/H/L/C; captures more information than Parkinson, still blind
    to opening jumps between sessions."""
    log_hl = np.log(df["High"] / df["Low"]) ** 2
    log_co = np.log(df["Close"] / df["Open"]) ** 2
    var_bar = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
    var = var_bar.rolling(window).mean()
    vol = np.sqrt(var.clip(lower=0))
    if annualize:
        vol = vol * np.sqrt(TRADING_DAYS_PER_YEAR)
    return vol


def yang_zhang_volatility(df: pd.DataFrame, window: int = 20, annualize: bool = True) -> pd.Series:
    """Combines overnight, open-to-close, and Rogers-Satchell terms; handles
    both overnight jumps and intraday drift, generally the most robust of
    the four estimators here."""
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    prev_c = c.shift(1)

    log_o_prevc = np.log(o / prev_c)
    log_c_o = np.log(c / o)
    log_h_o = np.log(h / o)
    log_l_o = np.log(l / o)

    overnight_var = log_o_prevc.rolling(window).var()
    open_close_var = log_c_o.rolling(window).var()
    rs_term = (log_h_o * (log_h_o - log_c_o) + log_l_o * (log_l_o - log_c_o)).rolling(window).mean()

    k = 0.34 / (1.34 + (window + 1) / (window - 1)) if window > 1 else 0.34
    var = overnight_var + k * open_close_var + (1 - k) * rs_term
    vol = np.sqrt(var.clip(lower=0))
    if annualize:
        vol = vol * np.sqrt(TRADING_DAYS_PER_YEAR)
    return vol


def volatility_percentile(vol_series: pd.Series, window: int = 100) -> pd.Series:
    """Where today's volatility ranks (0-1) against its own trailing window
    — used for compression/expansion detection rather than an absolute
    volatility cutoff, since 'high vol' means something different per name."""
    def _pct_rank(x):
        if np.isnan(x[-1]):
            return np.nan
        return (x <= x[-1]).mean()
    return vol_series.rolling(window).apply(_pct_rank, raw=True)


# --------------------------------------------------------------------------- §5 volume / liquidity

def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["Close"].diff()).fillna(0)
    return (direction * df["Volume"]).cumsum()


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP that resets every calendar day (session), approximated from the
    intraday bars actually available: typical-price * volume, grouped by
    date."""
    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv = typical * df["Volume"]
    day = df.index.date
    cum_pv = pv.groupby(day).cumsum()
    cum_vol = df["Volume"].groupby(day).cumsum()
    return cum_pv / cum_vol.replace(0, np.nan)


def relative_volume(volume: pd.Series, window: int = 20) -> pd.Series:
    return volume / volume.rolling(window).mean().replace(0, np.nan)


# --------------------------------------------------------------------------- §1 candle-level building blocks

def body_to_range_ratio(df: pd.DataFrame) -> pd.Series:
    body = (df["Close"] - df["Open"]).abs()
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    return body / rng


def wick_ratios(df: pd.DataFrame):
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    upper_wick = df["High"] - df[["Open", "Close"]].max(axis=1)
    lower_wick = df[["Open", "Close"]].min(axis=1) - df["Low"]
    return upper_wick / rng, lower_wick / rng


def close_location_value(df: pd.DataFrame) -> pd.Series:
    """0 = closed at the low, 1 = closed at the high of the bar's range."""
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    return (df["Close"] - df["Low"]) / rng


# --------------------------------------------------------------------------- master feature frame

def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Adds the original indicator columns plus the new §1/§2/§4/§5 building
    blocks used by the higher-level engines. Kept backward compatible: every
    column that existed before is still produced with the same name."""
    out = df.copy()

    # original set (unchanged names, still relied on by regime.py / strategies.py)
    out["sma_20"] = sma(out["Close"], 20)
    out["sma_50"] = sma(out["Close"], 50)
    out["ema_9"] = ema(out["Close"], 9)
    out["ema_21"] = ema(out["Close"], 21)
    out["rsi_14"] = rsi(out["Close"], 14)
    bb_u, bb_m, bb_l, bb_w = bollinger_bands(out["Close"], 20, 2.0)
    out["bb_upper"], out["bb_mid"], out["bb_lower"], out["bb_width"] = bb_u, bb_m, bb_l, bb_w
    out["atr_14"] = atr(out, 14)
    out["adx_14"] = adx(out, 14)

    # candle-level (§1)
    out["log_return_1"] = log_returns(out["Close"], 1)
    out["true_range"] = true_range(out)
    out["body_to_range"] = body_to_range_ratio(out)
    out["upper_wick_pct"], out["lower_wick_pct"] = wick_ratios(out)
    out["close_location"] = close_location_value(out)
    out["gap_pct"] = (out["Open"] - out["Close"].shift(1)) / out["Close"].shift(1)

    # trend / momentum (§2)
    out["slope_20"], out["r2_20"] = regression_slope_r2(out["Close"], 20)
    out["donchian_high_20"], out["donchian_low_20"] = donchian(out, 20)

    # volatility (§4)
    out["realized_vol_20"] = realized_volatility(out["Close"], 20)
    out["parkinson_vol_20"] = parkinson_volatility(out, 20)
    out["gk_vol_20"] = garman_klass_volatility(out, 20)
    out["yz_vol_20"] = yang_zhang_volatility(out, 20)
    out["vol_percentile_100"] = volatility_percentile(out["realized_vol_20"], 100)

    # volume / liquidity (§5) — only if a real Volume column is present
    if "Volume" in out.columns and out["Volume"].fillna(0).sum() > 0:
        out["rvol_20"] = relative_volume(out["Volume"], 20)
        out["obv"] = obv(out)
        try:
            out["vwap"] = session_vwap(out)
            out["vwap_dist_pct"] = (out["Close"] - out["vwap"]) / out["vwap"]
        except Exception:
            out["vwap"] = np.nan
            out["vwap_dist_pct"] = np.nan
    else:
        out["rvol_20"] = np.nan
        out["obv"] = np.nan
        out["vwap"] = np.nan
        out["vwap_dist_pct"] = np.nan

    return out
