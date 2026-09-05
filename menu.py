"""
Interactive menu for the signal engine. Run this and everything else is
point-and-pick from numbered options — no commands to remember.

    python menu.py
"""
import os
import sys
import json

import config
import state_store
import data_fetcher
import env_setup
import fidelity_import
import main as engine_main
import correlation_engine
import pattern_db
import ml_model

WATCHLIST_FILE = "watchlist.json"

BANNER = r"""
    ____  _________ __ __      _______   _____________   ________
   / __ \/  _/ ___// //_/     / ____/ | / / ____/  _/ | / / ____/
  / /_/ // / \__ \/ ,< ______/ __/ /  |/ / / __ / //  |/ / __/
 / _, _// / ___/ / /| /_____/ /___/ /|  / /_/ // // /|  / /___
/_/ |_/___//____/_/ |_|    /_____/_/ |_/\____/___/_/ |_/_____/

    ___    __    _________
   /   |  / /   / ____/   |
  / /| | / /   / /_  / /| |
 / ___ |/ /___/ __/ / ___ |
/_/  |_/_____/_/   /_/  |_|
"""


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def pause():
    input("\nPress Enter to return to the menu...")


def load_watchlist() -> list:
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE) as f:
            return json.load(f)
    return ["AAPL", "MSFT", "SPY", "QQQ", "NVDA", "TSLA", "AMD", "GOOGL", "AMZN", "META",
            "AVGO", "NFLX", "PLTR", "CRM", "COIN", "MSTR", "SMCI", "ARM", "SOFI", "RIVN",
            "XLK", "XLF", "XLE", "SMH", "IWM"]


def save_watchlist(wl: list):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(wl, f)


def header(title: str, show_banner: bool = False):
    clear()
    if show_banner:
        print(BANNER)
    print("=" * 66)
    print(f"  {title}")
    print("=" * 66)


# ---------------------------------------------------------------- menu items

def menu_run_scan_once():
    header("RUN ONE SCAN")
    wl = load_watchlist()
    print(f"Watchlist: {', '.join(wl)}\n")
    engine_main.run_once(wl)
    pause()


def menu_watch_continuously():
    header("WATCH CONTINUOUSLY")
    wl = load_watchlist()
    print(f"Watchlist: {', '.join(wl)}")
    interval_raw = input("Scan every how many seconds? [300]: ").strip()
    interval = int(interval_raw) if interval_raw else 300
    ignore_hours = input("Ignore market-hours check (for testing)? [y/N]: ").strip().lower() == "y"
    print("\nStarting watch loop. Press Ctrl+C to stop and return to the menu.\n")
    try:
        import time
        import pytz
        from datetime import datetime
        while True:
            now_utc = datetime.now(pytz.utc)
            if ignore_hours or engine_main.market_is_open(now_utc):
                try:
                    engine_main.run_once(wl)
                except Exception as e:
                    print(f"[scan error] {e}")
            else:
                print(f"[{now_utc.strftime('%H:%M:%S UTC')}] Market closed — sleeping.")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    pause()


def menu_status():
    header("ACCOUNT & RISK STATUS")
    state = state_store.load()
    day_trades = state_store.day_trade_count_last_5_sessions(state)
    print(f"Equity:            ${state['equity']:,.2f}")
    print(f"Peak equity:       ${state['peak_equity']:,.2f}")
    print(f"Daily P&L:         ${state['daily_pnl']:,.2f}")
    print(f"Day trades (~5d):  {day_trades}")
    print(f"Open positions:")
    if state["open_positions"]:
        for sym, pos in state["open_positions"].items():
            print(f"   {sym}: {pos['qty']} shares @ avg ${pos['avg_price']:.2f}")
    else:
        print("   (none)")
    print(f"\nTotal trades logged: {len(state['trade_history'])}")
    pause()


def menu_set_equity():
    header("SET ACCOUNT EQUITY")
    print("Enter your current total Fidelity account value (cash + positions).\n")
    raw = input("Current equity ($): ").strip()
    try:
        equity = float(raw.replace(",", "").replace("$", ""))
    except ValueError:
        print("That doesn't look like a number.")
        pause()
        return
    state = state_store.set_equity(equity)
    print(f"\nEquity set to ${equity:,.2f} (peak now ${state['peak_equity']:,.2f})")
    pause()


def menu_log_trade():
    header("LOG A TRADE FILL")
    print("Log the trade AFTER you place it on Fidelity, using your actual fill.\n")
    symbol = input("Symbol (e.g. AAPL): ").strip().upper()
    if not symbol:
        return
    side = ""
    while side not in ("BUY", "SELL"):
        side = input("Side (BUY/SELL): ").strip().upper()
    try:
        qty = float(input("Quantity (shares): ").strip())
        price = float(input("Fill price ($): ").strip().replace("$", ""))
    except ValueError:
        print("That doesn't look like a number.")
        pause()
        return
    state_store.log_trade(symbol, side, qty, price)
    print(f"\nLogged {side} {qty} {symbol} @ ${price:.2f}")
    pause()


def menu_edit_watchlist():
    header("EDIT WATCHLIST")
    wl = load_watchlist()
    print(f"Current watchlist: {', '.join(wl)}\n")
    raw = input("Enter new comma-separated watchlist (blank = keep current): ").strip()
    if raw:
        new_wl = [s.strip().upper() for s in raw.split(",") if s.strip()]
        save_watchlist(new_wl)
        print(f"\nWatchlist updated: {', '.join(new_wl)}")
    else:
        print("Unchanged.")
    pause()


def menu_view_config():
    header("CURRENT RISK CONFIG (edit config.py to change)")
    print(f"Account type:              {config.ACCOUNT_TYPE}")
    print(f"PDT threshold:             ${config.PDT_THRESHOLD:,.0f}")
    print(f"Risk per trade:            {config.RISK_PER_TRADE_PCT:.1%}")
    print(f"Max daily loss:            {config.MAX_DAILY_LOSS_PCT:.1%}")
    print(f"Max drawdown from peak:    {config.MAX_DRAWDOWN_FROM_PEAK_PCT:.1%}")
    print(f"Max position concentration:{config.MAX_POSITION_CONCENTRATION_PCT:.1%}")
    print(f"Max open positions:        {config.MAX_OPEN_POSITIONS}")
    active = data_fetcher.active_sources()
    print(f"\nActive data sources (in fallback order): {', '.join(active) if active else '(none configured — will error)'}")
    pause()


def menu_setup_api_keys():
    global config
    header("SET UP API KEYS & EMAIL ALERTS")
    print("Enter a key to add/update it, or press Enter to leave it unchanged.")
    print("You can set up as many of these as you want — the engine tries them")
    print("in this order every scan and falls back automatically if one fails")
    print("or has no key configured. yfinance always works with no key at all.")
    print("Email alerts are optional and separate from data sources — see the")
    print("last section below.\n")

    current = env_setup.read_env()
    updates = {}

    for provider_id, info in config.API_KEY_REGISTRY.items():
        configured = all(current.get(v) for v in info["env_vars"])
        status = "already set" if configured else "not set"
        print(f"--- {info['label']}  [{status}] ---")
        print(f"    {info['note']}")
        print(f"    Sign up: {info['signup_url']}")
        for var in info["env_vars"]:
            existing = current.get(var, "")
            masked = (existing[:4] + "…") if existing else "(blank)"
            raw = input(f"    {var} [{masked}]: ").strip()
            if raw:
                updates[var] = raw
        print()

    if updates:
        env_setup.write_env(updates)
        config = env_setup.reload_config()
        print(f"Saved {len(updates)} key(s) to .env and reloaded config.")
        active = data_fetcher.active_sources()
        print(f"Active data sources now (in order): {', '.join(active)}")
        if config.EMAIL_ENABLED:
            test = input("\nEmail alerts are configured. Send a test email now? [y/N]: ").strip().lower()
            if test == "y":
                import notifier
                if notifier.send_test_email():
                    print(f"Test email sent to {config.EMAIL_TO} — check your inbox (and spam folder).")
                else:
                    print("Test email failed to send — see the error above.")
    else:
        print("No changes made.")
    pause()


def menu_import_fidelity():
    header("IMPORT FIDELITY TRADE HISTORY")
    print("Reads a Fidelity account history CSV export and backfills your")
    print("REAL trade dates into state.json, so PDT day-trade counting")
    print("reflects what actually happened rather than starting from zero.")
    print()
    print("This does NOT set your account equity — Fidelity's 'Cash Balance'")
    print("column is margin cash (can be legitimately negative while trading")
    print("on margin), not total account equity. Keep using option 4 for that.\n")

    candidates = fidelity_import.find_candidate_csvs()
    path = None
    if candidates:
        print("Found these CSV files nearby:")
        for i, p in enumerate(candidates, start=1):
            print(f"  {i}. {p}")
        print(f"  0. Enter a different path")
        choice = input("\nChoose a file: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            path = candidates[int(choice) - 1]
    if not path:
        path = input("Full path to the Fidelity CSV: ").strip().strip('"').strip("'")

    if not path or not os.path.exists(path):
        print(f"\nCouldn't find file: {path}")
        pause()
        return

    try:
        result = fidelity_import.import_into_state(path)
    except Exception as e:
        print(f"\nImport failed: {e}")
        pause()
        return

    print(f"\nImported {result['trades_imported']} trade(s) from the file.")

    if result["day_trades_found"]:
        print(f"\nConfirmed day trades (opened + closed same day):")
        for dt in result["day_trades_found"]:
            print(f"   {dt['date']}: {dt['symbol']}")
    else:
        print("\nNo same-day round-trip trades found in this file.")

    if result["unmatched_sells"]:
        print(f"\nSells that closed a position opened before this file's coverage")
        print("(correctly NOT counted as day trades):")
        for s in result["unmatched_sells"]:
            print(f"   {s['date']}: {s['symbol']}")

    if result["latest_cash_balance"] is not None:
        print(f"\nMost recent settled Fidelity cash balance in the file: "
              f"${result['latest_cash_balance']:,.2f}")
        print("(Margin cash, not total equity — set your real equity with option 4.)")

    state = state_store.load()
    day_trades_now = state_store.day_trade_count_last_5_sessions(state)
    print(f"\nCurrent day-trade count in the rolling PDT window: {day_trades_now}")
    if config.ACCOUNT_TYPE == "margin" and day_trades_now >= config.PDT_MAX_DAY_TRADES_PER_5_DAYS:
        print("WARNING: at or over the PDT day-trade limit for a margin account")
        print("under $25,000 equity. New day trades will be BLOCKED by the risk engine.")
    pause()


def menu_correlation_dashboard():
    header("CORRELATION & RELATIVE STRENGTH DASHBOARD")
    bars = engine_main.last_scan_bars
    if len(bars) < 3:
        print("Run a scan (option 1) first — this dashboard reuses that scan's bars\n"
              "so it doesn't cost extra API calls. Need at least 3 symbols with data.")
        pause()
        return

    print(f"Universe ({len(bars)} symbols): {', '.join(bars.keys())}\n")
    corr = correlation_engine.correlation_matrix(bars)
    if corr.empty:
        print("Not enough overlapping history to build a correlation matrix yet.")
        pause()
        return

    print(f"Pairwise return correlation, last {config.CORRELATION_LOOKBACK} bars:\n")
    print(corr.round(2).to_string())

    flags = correlation_engine.detect_unusual_correlations(corr)
    print("\nUnusually HIGH correlation pairs (>= 0.90):")
    if flags["high_correlation_pairs"]:
        for a, b, v in flags["high_correlation_pairs"]:
            print(f"   {a} <-> {b}: {v}")
    else:
        print("   (none)")

    print("\nCorrelation BREAKDOWN pairs (near zero, |corr| <= 0.10):")
    if flags["low_correlation_pairs"]:
        for a, b, v in flags["low_correlation_pairs"]:
            print(f"   {a} <-> {b}: {v}")
    else:
        print("   (none)")

    print("\nRelative strength vs benchmark, from the last scan:")
    rs_rows = sorted(
        [(r["symbol"], r.get("relative_strength_pct")) for r in engine_main.last_scan_results
         if r.get("relative_strength_pct") is not None],
        key=lambda t: -t[1],
    )
    for sym, rs in rs_rows:
        print(f"   {sym:<8} {rs:+.2f}%")
    pause()


def menu_pattern_research():
    header("PATTERN RESEARCH & STATISTICAL SIGNAL ENGINE")
    print("Backfilling forward returns for old-enough logged observations...")
    try:
        n = pattern_db.backfill_forward_returns(data_fetcher.get_bars)
        print(f"Backfilled {n} observation(s).\n")
    except Exception as e:
        print(f"Backfill failed: {e}\n")

    print("=== Pattern stats (10-bar forward return; needs >= 5 samples/pattern) ===")
    df = pattern_db.pattern_stats("pattern", 10)
    print(df.to_string(index=False) if not df.empty else "(not enough labeled data yet)")

    print("\n=== Regime stats (10-bar forward return) ===")
    df = pattern_db.pattern_stats("regime", 10)
    print(df.to_string(index=False) if not df.empty else "(not enough labeled data yet)")

    print("\n=== Information Coefficients (does this feature predict forward returns?) ===")
    any_ic = False
    for feat in ("composite_score", "trend_score", "momentum_score", "rvol",
                 "mean_reversion_score", "relative_strength_score"):
        ic = pattern_db.information_coefficient(feat, 10)
        if ic:
            any_ic = True
            print(f"   {ic['feature']:<26} IC={ic['information_coefficient']:+.3f}  (n={ic['n']})")
    if not any_ic:
        print("   (not enough labeled data yet)")

    print(f"\nRun scans regularly (option 1/2) to keep building history in "
          f"{config.PATTERN_DB_PATH} — forward returns need time to actually happen "
          "before they can be backfilled and analyzed.")
    pause()


def menu_train_ml():
    header("TRAIN / UPDATE ML MODEL")
    print("Trains on labeled rows in the pattern database (run option 11 first to\n"
          "backfill forward returns). Needs "
          f"{config.ML_MIN_TRAINING_ROWS}+ labeled observations to train at all.\n")
    result = ml_model.train()
    if result.get("trained"):
        print(f"Trained {result['model_name']} on {result['trained_on_rows']} rows.")
        print(f"Held-out test accuracy: {result['test_accuracy']:.1%}")
        print(f"\nSaved to {config.ML_MODEL_PATH} — future scans will now include the ML vote.")
    else:
        print(f"Not trained: {result.get('reason')}")
    pause()


HELP_TEXT = """
HOW EACH MENU OPTION WORKS
---------------------------------------------------------------

1. RUN ONE SIGNAL SCAN NOW
   Pulls fresh bars for every symbol on your watchlist plus the
   benchmark (SPY by default), then runs the full multi-layer pipeline
   per symbol: momentum/trend, mean-reversion, volatility, volume,
   market structure, relative strength vs benchmark, multi-timeframe
   trend alignment, candle pattern/swing structure, and (once trained)
   an ML vote. Those engine scores are combined by signal fusion into
   one composite score (-1..+1), a label (STRONG LONG..STRONG SHORT),
   and a confidence %, which then goes through the risk engine. Prints
   one table, appends every row to signals_log.csv, and logs a research
   observation to the pattern database for later analysis (option 11).

2. WATCH CONTINUOUSLY
   Same as option 1, but repeats automatically on a timer, and skips
   scans when the market is closed (9:30-16:00 ET, Mon-Fri) unless you
   choose to ignore market hours (useful for testing on a weekend).
   Press Ctrl+C at any time to stop and return to this menu.

3. VIEW ACCOUNT & RISK STATUS
   Shows your current logged equity, peak equity, today's P&L, how
   many day trades you've logged in the rolling PDT window, and any
   open positions. This is read-only — it reflects whatever you've
   told the engine via options 4 and 5, not a live Fidelity feed.

4. SET ACCOUNT EQUITY
   Tells the engine your real total Fidelity account value. This
   number drives every risk calculation: position sizing, the daily
   loss halt, and the drawdown pause. Update it whenever your balance
   materially changes — the risk engine is only as accurate as this.

5. LOG A TRADE FILL
   Records a BUY or SELL you actually placed at Fidelity, with your
   real fill price and quantity. This is what lets the engine track
   which positions are open, how many day trades you've made (for the
   PDT rule), and your realized P&L. Log every fill, every time.

6. EDIT WATCHLIST
   Sets the list of tickers scanned by options 1 and 2. Saved to
   watchlist.json so you don't have to re-enter it each session.

7. VIEW CURRENT RISK CONFIG
   Shows the numeric risk parameters currently in effect (risk per
   trade, max daily loss, max drawdown, position concentration cap,
   PDT threshold) and which data sources are active. These numbers
   live in config.py — edit that file directly to change them
   permanently; this screen is read-only.

8. SET UP API KEYS & EMAIL ALERTS
   Add or update keys for Alpaca and any of the free fallback data
   providers (Finnhub, Twelve Data, Alpha Vantage, Polygon, Tiingo,
   Financial Modeling Prep) without touching any files by hand. You
   can configure as many as you like — the engine tries them in
   priority order on every scan and automatically moves to the next
   one if a provider is unconfigured, rate-limited, or errors out.
   yfinance needs no key and is always the final fallback.

   Also configures optional EMAIL ALERTS on this same screen — enter
   your email address, an App Password (Gmail: turn on 2-Step
   Verification, then generate one — your normal password won't
   work), and where to send alerts. Once set up, you'll be offered a
   one-click test email so you're not waiting for a real signal to
   confirm it works. Every alert email includes the full strategy
   explanation and exact sell/exit conditions, not just the numbers.

9. IMPORT FIDELITY TRADE HISTORY
   Reads a Fidelity account history CSV export (Accounts > History >
   Download) and backfills your real trade dates into state.json.
   This is what makes the PDT day-trade count trustworthy from day
   one instead of only counting trades you log going forward. It
   detects genuine same-day round trips versus sells that closed a
   position opened before the file's coverage window, and reports
   both. It does not touch your account equity.

10. CORRELATION & RELATIVE-STRENGTH DASHBOARD
   Reuses the bars from your last scan (run option 1 first) to build a
   pairwise return-correlation matrix across your watchlist + the
   benchmark, flags pairs that are unusually highly correlated or that
   have broken down (correlation near zero), and ranks symbols by
   relative strength vs the benchmark. This is the foundation for
   pair-trading / statistical-arbitrage research, not a trade signal.

11. PATTERN RESEARCH (edge stats & IC on logged history)
   Every scan logs one observation per symbol into pattern_db.sqlite.
   This option backfills forward returns (+1/+5/+10/+20 bars) for
   observations old enough that those bars now exist, then reports,
   per candle pattern and per regime: sample size, average forward
   return, win rate, and a simple Sharpe-like ratio — plus the
   Information Coefficient (correlation with future returns) for each
   continuous engine score. This answers the engine's core question:
   does this feature/pattern actually predict anything, empirically?
   Needs real history to say anything meaningful — expect "not enough
   labeled data yet" until you've run scans regularly for a while.

12. TRAIN / UPDATE ML MODEL
   Trains a classifier (logistic regression, or gradient boosting once
   there's enough data) on the labeled rows in the pattern database to
   predict whether the next 10 bars will be positive, using the same
   engine scores you already see in the scan table. Requires
   scikit-learn and enough labeled history (see config.ML_MIN_TRAINING_ROWS).
   Once trained, future scans automatically include its vote in the
   composite score.

13. HELP
   This screen.

0. EXIT
   Closes the program. Nothing runs in the background after this —
   if you chose "watch continuously," stop it with Ctrl+C first.

---------------------------------------------------------------
KEY CONCEPTS

Regime:      Per-symbol: trending / ranging / choppy, from ADX and
             Bollinger Band width (still used to size ATR-based
             stops/targets). Market-wide: TRENDING_BULL, TRENDING_BEAR,
             LOW_VOL_RANGE, HIGH_VOL_RANGE, BREAKOUT, PANIC, or
             RECOVERY, derived from the benchmark (SPY by default) and
             used to scale how much confidence the composite score gets.

Signal fusion: No single indicator ever triggers a BUY/SELL by itself.
             Eight engines (trend, momentum, mean-reversion, volume,
             structure, relative strength, multi-timeframe alignment,
             and — once trained — ML) each vote a score from -1 to +1.
             Those votes are weighted (config.ENGINE_WEIGHTS), scaled by
             the volatility engine's confidence multiplier and the
             market-regime multiplier, and combined into one composite
             score. The composite score maps to STRONG LONG / LONG /
             WATCH / NEUTRAL / SHORT / STRONG SHORT (config.COMPOSITE_
             THRESHOLDS); only LONG/STRONG LONG/SHORT/STRONG SHORT ever
             produce a tradeable side — WATCH and NEUTRAL are always HOLD.

Risk status: Every non-HOLD signal is stamped APPROVED or BLOCKED
             before you ever see it. BLOCKED always comes with a
             plain-English reason (PDT limit, daily loss hit,
             drawdown pause, max positions, etc.). The risk engine
             never sees or adjusts the composite score — alpha and
             risk are kept deliberately separate.

Pattern database: Every scan is logged as one research observation.
             Options 11/12 turn that log into empirical pattern/regime
             statistics and, eventually, a trained model — the
             "does this actually predict anything" layer the doc calls
             the most important part of the whole system.

Why manual execution: Fidelity has no public trading API, so this
             tool never places a real order. It tells you exactly
             what to do (symbol, side, quantity, entry, stop, target)
             and you execute it yourself at Fidelity, then log the
             fill with option 5 so the risk engine stays accurate.
"""


def menu_help():
    header("HELP", show_banner=False)
    print(HELP_TEXT)
    pause()


MENU = [
    ("Run one signal scan now", menu_run_scan_once),
    ("Watch continuously (auto-scan on an interval)", menu_watch_continuously),
    ("View account & risk status", menu_status),
    ("Set account equity", menu_set_equity),
    ("Log a trade fill", menu_log_trade),
    ("Edit watchlist", menu_edit_watchlist),
    ("View current risk config", menu_view_config),
    ("Set up API keys", menu_setup_api_keys),
    ("Import Fidelity trade history (CSV)", menu_import_fidelity),
    ("Correlation & relative-strength dashboard", menu_correlation_dashboard),
    ("Pattern research (edge stats & IC on logged history)", menu_pattern_research),
    ("Train / update ML model", menu_train_ml),
    ("Help — detailed instructions for every option", menu_help),
]


def main():
    while True:
        header("MAIN MENU", show_banner=True)
        for i, (label, _) in enumerate(MENU, start=1):
            print(f"  {i}. {label}")
        print(f"  0. Exit")
        choice = input("\nChoose an option: ").strip()

        if choice == "0":
            print("Goodbye.")
            sys.exit(0)

        try:
            idx = int(choice) - 1
            if idx < 0:
                raise ValueError
            _, func = MENU[idx]
            func()
        except (ValueError, IndexError):
            print("Not a valid option.")
            pause()


if __name__ == "__main__":
    main()
