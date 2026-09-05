"""
Signal engine main loop.

    python main.py --watchlist AAPL,MSFT,SPY,QQQ,NVDA --interval 300
    python main.py --watchlist AAPL,MSFT --once

Prints a signal table to console and appends every row to signals_log.csv.
Nothing here places real orders — Fidelity has no API. This tells you what
to do; you do it.
"""
import argparse
import csv
import os
import time
from datetime import datetime

import pytz
from tabulate import tabulate

import config
import signal_engine
import data_fetcher
import indicators
import regime as regime_mod
import notifier

# Populated by every run_once() call so menu.py's correlation/RS dashboard
# can reuse the same bars without re-fetching.
last_scan_bars: dict = {}
last_scan_results: list = []


def market_is_open(now_utc: datetime) -> bool:
    tz = pytz.timezone(config.MARKET_TZ)
    now_local = now_utc.astimezone(tz)
    if now_local.weekday() >= 5:  # Sat/Sun
        return False
    open_h, open_m = map(int, config.MARKET_OPEN.split(":"))
    close_h, close_m = map(int, config.MARKET_CLOSE.split(":"))
    open_t = now_local.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    close_t = now_local.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    return open_t <= now_local <= close_t


_CSV_FIELDS = [
    "symbol", "timestamp", "bar_time", "regime", "market_regime", "adx", "bb_width_pct",
    "strategy", "side", "signal_label", "composite_score", "confidence_pct", "reason",
    "entry", "stop", "target", "risk_status", "risk_reason", "suggested_qty",
    "pattern", "swing_structure", "is_anomaly", "rvol", "vol_state",
    "relative_strength_pct", "ml_available",
]


def append_csv(rows: list):
    flat_rows = [{k: r.get(k) for k in _CSV_FIELDS} for r in rows]
    file_exists = os.path.exists(config.SIGNAL_LOG_CSV)
    with open(config.SIGNAL_LOG_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(flat_rows)


_alerted_bars = set()  # (symbol, bar_time) already surfaced as ACTIONABLE this run


def _fetch_benchmark():
    """Fetches and indicator-computes the benchmark once per scan (§7, §9).
    Returns (raw_df, indicator_df) — both empty DataFrames on failure so
    every downstream engine degrades gracefully instead of raising."""
    try:
        raw = data_fetcher.get_bars(config.BENCHMARK_SYMBOL)
        if raw.empty or len(raw) < 55:
            return raw, raw
        return raw, indicators.compute_all(raw)
    except Exception as e:
        print(f"[main] Benchmark fetch failed ({config.BENCHMARK_SYMBOL}): {e}")
        import pandas as pd
        return pd.DataFrame(), pd.DataFrame()


def run_once(watchlist: list) -> list:
    global last_scan_bars, last_scan_results

    benchmark_raw, benchmark_ind = _fetch_benchmark()
    market_regime_info = regime_mod.classify_market_regime(benchmark_ind)

    results = []
    bars_by_symbol = {}
    if not benchmark_raw.empty:
        bars_by_symbol[config.BENCHMARK_SYMBOL] = benchmark_raw
    for sym in watchlist:
        raw = data_fetcher.get_bars(sym)
        if not raw.empty:
            bars_by_symbol[sym] = raw
        r = signal_engine.run_for_symbol(sym, benchmark_df=benchmark_raw,
                                          benchmark_df_ind=benchmark_ind,
                                          market_regime_info=market_regime_info,
                                          raw_df=raw if not raw.empty else None)
        results.append(r)

    last_scan_bars = bars_by_symbol
    last_scan_results = results

    table = [[r["symbol"], r["market_regime"], r["regime"], r["signal_label"],
              r["composite_score"], f"{r['confidence_pct']:.0f}%", r["side"],
              r["entry"], r["stop"], r["target"], r["suggested_qty"],
              r["risk_status"]] for r in results]
    headers = ["Symbol", "Mkt Regime", "Regime", "Signal", "Score", "Conf",
               "Side", "Entry", "Stop", "Target", "Qty", "Risk"]
    print(f"\n=== Signal scan @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
          f"(data sources: {', '.join(data_fetcher.active_sources())}; "
          f"benchmark: {config.BENCHMARK_SYMBOL} -> {market_regime_info.get('regime')}) ===")
    print(tabulate(table, headers=headers, tablefmt="simple"))
    append_csv(results)

    new_actionable = []
    for r in results:
        if r["side"] != "HOLD" and r["risk_status"] == "APPROVED":
            key = (r["symbol"], r["bar_time"])
            if key not in _alerted_bars:
                _alerted_bars.add(key)
                new_actionable.append(r)

    if new_actionable:
        print("\n>>> NEW ACTIONABLE — place these manually on Fidelity:")
        for r in new_actionable:
            reasons = "; ".join(r["reasons"][:3]) if r.get("reasons") else r["strategy"]
            print(f"    {r['side']} {r['suggested_qty']} {r['symbol']} @ ~{r['entry']} "
                  f"| stop {r['stop']} | target {r['target']}  "
                  f"[{r['signal_label']} {r['confidence_pct']:.0f}%]  ({reasons})")
        notifier.maybe_send(new_actionable)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watchlist", required=True, help="Comma-separated tickers, e.g. AAPL,MSFT,SPY")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between scans")
    parser.add_argument("--once", action="store_true", help="Run a single scan and exit")
    parser.add_argument("--ignore-market-hours", action="store_true",
                         help="Run even outside 9:30-16:00 ET (useful for testing)")
    args = parser.parse_args()

    watchlist = [s.strip().upper() for s in args.watchlist.split(",") if s.strip()]

    if args.once:
        run_once(watchlist)
        return

    print(f"Watching {watchlist} every {args.interval}s. Ctrl+C to stop.")
    while True:
        now_utc = datetime.now(pytz.utc)
        if args.ignore_market_hours or market_is_open(now_utc):
            try:
                run_once(watchlist)
            except Exception as e:
                print(f"[main] Scan error: {e}")
        else:
            print(f"[{now_utc.strftime('%H:%M:%S UTC')}] Market closed — sleeping.")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
