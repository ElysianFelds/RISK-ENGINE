"""
§11/§12/§20 — Candle Pattern Research Engine + Statistical Signal Engine.

Every scanned bar becomes one labeled observation in a local SQLite file
(config.PATTERN_DB_PATH). Forward returns (+1/+5/+10/+20 bar) get filled in
later, once enough time has passed, by `backfill_forward_returns()`. Once
labeled, `pattern_stats()` and `information_coefficient()` answer the
doc's central question: does this feature/pattern actually predict future
returns, and under what conditions?

This intentionally stays on plain sqlite3 + pandas — no extra services to
run — so `python pattern_db.py research` works out of the box.
"""
import json
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

import config

FORWARD_HORIZONS = (1, 5, 10, 20)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    bar_time TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    entry_price REAL,
    pattern TEXT,
    swing_structure TEXT,
    regime TEXT,
    market_regime TEXT,
    vol_state TEXT,
    rvol REAL,
    trend_score REAL,
    momentum_score REAL,
    mean_reversion_score REAL,
    volume_score REAL,
    structure_score REAL,
    relative_strength_score REAL,
    composite_score REAL,
    side TEXT,
    features_json TEXT,
    fwd_ret_1 REAL,
    fwd_ret_5 REAL,
    fwd_ret_10 REAL,
    fwd_ret_20 REAL,
    mfe REAL,
    mae REAL,
    UNIQUE(symbol, bar_time)
);
"""


def _connect():
    conn = sqlite3.connect(config.PATTERN_DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def log_observation(record: dict) -> None:
    """record should contain the keys referenced in _SCHEMA (extras go into
    features_json). Silently upserts — re-scanning the same bar just
    updates the row rather than duplicating it."""
    conn = _connect()
    cols = ["symbol", "bar_time", "logged_at", "entry_price", "pattern", "swing_structure",
            "regime", "market_regime", "vol_state", "rvol", "trend_score", "momentum_score",
            "mean_reversion_score", "volume_score", "structure_score",
            "relative_strength_score", "composite_score", "side", "features_json"]
    values = [record.get(c) for c in cols]
    placeholders = ",".join(["?"] * len(cols))
    col_list = ",".join(cols)
    update_clause = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("symbol", "bar_time"))
    conn.execute(
        f"INSERT INTO observations ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT(symbol, bar_time) DO UPDATE SET {update_clause}",
        values,
    )
    conn.commit()
    conn.close()


def backfill_forward_returns(get_bars_fn) -> int:
    """For rows old enough that +20-bar forward data should now exist,
    fetches fresh bars for that symbol and fills in fwd_ret_1/5/10/20, MFE,
    and MAE. `get_bars_fn(symbol)` should be data_fetcher.get_bars (injected
    to avoid a circular import). Returns the number of rows updated."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, symbol, bar_time, entry_price FROM observations WHERE fwd_ret_20 IS NULL"
    ).fetchall()

    updated = 0
    bars_cache = {}
    for row_id, symbol, bar_time, entry_price in rows:
        if entry_price is None:
            continue
        if symbol not in bars_cache:
            try:
                bars_cache[symbol] = get_bars_fn(symbol)
            except Exception:
                bars_cache[symbol] = pd.DataFrame()
        bars = bars_cache[symbol]
        if bars.empty:
            continue

        try:
            bar_ts = pd.Timestamp(bar_time)
        except Exception:
            continue
        idx = bars.index
        # position of the first bar strictly after the observation's bar_time
        after = idx[idx > bar_ts]
        if after.empty:
            continue
        start_pos = idx.get_loc(after[0])

        max_h = max(FORWARD_HORIZONS)
        if len(bars) < start_pos + max_h:
            continue  # not enough future bars fetched yet — try again next backfill run

        window = bars.iloc[start_pos:start_pos + max_h]
        fwd = {h: float(window["Close"].iloc[h - 1] / entry_price - 1.0) for h in FORWARD_HORIZONS}
        mfe = float(window["High"].max() / entry_price - 1.0)
        mae = float(window["Low"].min() / entry_price - 1.0)

        conn.execute(
            "UPDATE observations SET fwd_ret_1=?, fwd_ret_5=?, fwd_ret_10=?, fwd_ret_20=?, mfe=?, mae=? WHERE id=?",
            (fwd[1], fwd[5], fwd[10], fwd[20], mfe, mae, row_id),
        )
        updated += 1

    conn.commit()
    conn.close()
    return updated


def load_labeled(min_rows: int = 1) -> pd.DataFrame:
    conn = _connect()
    df = pd.read_sql_query("SELECT * FROM observations WHERE fwd_ret_10 IS NOT NULL", conn)
    conn.close()
    return df if len(df) >= min_rows else pd.DataFrame()


def pattern_stats(group_by: str = "pattern", horizon: int = 10, min_samples: int = 5) -> pd.DataFrame:
    """§11/§19: for each distinct value of `group_by` (pattern, regime,
    vol_state, ...), empirically measures avg forward return, win rate, and
    a simple Sharpe-like ratio (mean/std of the forward return), per the
    doc's example: '+0.8% average 10-bar return, 57% win rate, 1.35 Sharpe'."""
    df = load_labeled()
    if df.empty or group_by not in df.columns:
        return pd.DataFrame()

    col = f"fwd_ret_{horizon}"
    if col not in df.columns:
        return pd.DataFrame()

    rows = []
    for key, sub in df.groupby(group_by):
        sub = sub.dropna(subset=[col])
        if len(sub) < min_samples:
            continue
        mean_ret = sub[col].mean()
        std_ret = sub[col].std()
        win_rate = (sub[col] > 0).mean()
        sharpe = mean_ret / std_ret if std_ret else np.nan
        rows.append({
            group_by: key, "n": len(sub),
            f"avg_fwd_ret_{horizon}_pct": round(mean_ret * 100, 3),
            "win_rate_pct": round(win_rate * 100, 1),
            "sharpe_like": None if pd.isna(sharpe) else round(float(sharpe), 2),
        })

    return pd.DataFrame(rows).sort_values(f"avg_fwd_ret_{horizon}_pct", ascending=False)


def information_coefficient(feature_col: str, horizon: int = 10, min_samples: int = 20) -> "dict | None":
    """§12: IC = corr(signal, future return). Tells you whether a
    continuous feature (e.g. composite_score, rvol, trend_score) actually
    carries predictive information, independent of any pattern label."""
    df = load_labeled()
    col = f"fwd_ret_{horizon}"
    if df.empty or feature_col not in df.columns or col not in df.columns:
        return None
    sub = df.dropna(subset=[feature_col, col])
    if len(sub) < min_samples:
        return None
    ic = sub[feature_col].astype(float).corr(sub[col].astype(float))
    if pd.isna(ic):
        return None
    return {"feature": feature_col, "horizon": horizon, "n": len(sub), "information_coefficient": round(float(ic), 3)}


if __name__ == "__main__":
    import sys
    import data_fetcher

    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        n = backfill_forward_returns(data_fetcher.get_bars)
        print(f"Backfilled forward returns for {n} observation(s).")
    elif len(sys.argv) > 1 and sys.argv[1] == "research":
        print("=== Pattern stats (10-bar forward return) ===")
        print(pattern_stats("pattern", 10).to_string(index=False))
        print("\n=== Regime stats (10-bar forward return) ===")
        print(pattern_stats("regime", 10).to_string(index=False))
        print("\n=== Information coefficients ===")
        for feat in ("composite_score", "trend_score", "momentum_score", "rvol",
                     "mean_reversion_score", "relative_strength_score"):
            ic = information_coefficient(feat, 10)
            if ic:
                print(ic)
    else:
        print(__doc__)
        print("Usage:\n  python pattern_db.py backfill   # fill in forward returns for older rows\n"
              "  python pattern_db.py research    # print pattern/regime edge stats + IC")
