"""
Parses a Fidelity 'Accounts_History' CSV export and backfills your real
trade history into state.json — with the ACTUAL historical dates, not
today's date — so PDT day-trade counting reflects what really happened.

Does NOT touch account equity. Fidelity's "Cash Balance" column in this
export is margin cash (can be legitimately negative while trading on
margin), not total account equity, so it's reported for reference only.
Set your real equity with menu option 4.
"""
import csv as csvmod
import glob
import os
import re
from datetime import datetime

import state_store

TRADE_ACTION_RE = re.compile(r"^YOU (BOUGHT|SOLD)\b")


def find_candidate_csvs() -> list:
    """Looks in the current folder, ~/Downloads, and (on WSL) the Windows
    Downloads folder for CSV files, newest first."""
    dirs = [".", os.path.expanduser("~/Downloads")]
    dirs.extend(glob.glob("/mnt/c/Users/*/Downloads"))
    found, seen = [], set()
    for d in dirs:
        if os.path.isdir(d):
            for f in sorted(glob.glob(os.path.join(d, "*.csv")),
                             key=os.path.getmtime, reverse=True):
                real = os.path.abspath(f)
                if real not in seen:
                    found.append(real)
                    seen.add(real)
    return found[:10]


def parse_fidelity_csv(path: str):
    """Returns (trades, latest_cash_balance).
    trades: chronological (oldest-first) list of dicts with date/symbol/side/qty/price.
    latest_cash_balance: most recent settled (non-"Processing") cash balance found, or None.
    """
    trades = []
    dated_balances = []

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csvmod.DictReader(f)
        for row in reader:
            run_date = (row.get("Run Date") or "").strip()
            if not run_date:
                continue
            try:
                date = datetime.strptime(run_date, "%m/%d/%Y")
            except ValueError:
                continue  # footer/disclaimer rows etc.

            action = (row.get("Action") or "").strip()
            symbol = (row.get("Symbol") or "").strip()
            if TRADE_ACTION_RE.match(action) and symbol:
                try:
                    qty = float(row["Quantity"])
                    price = float(row["Price ($)"])
                except (ValueError, KeyError, TypeError):
                    pass
                else:
                    trades.append({
                        "date": date, "symbol": symbol,
                        "side": "BUY" if qty > 0 else "SELL",
                        "qty": abs(qty), "price": price,
                    })

            bal_raw = (row.get("Cash Balance ($)") or "").strip()
            if bal_raw and bal_raw.lower() != "processing":
                try:
                    dated_balances.append((date, float(bal_raw.replace(",", ""))))
                except ValueError:
                    pass

    # The file is consistently ordered newest -> oldest, including the
    # order of same-day transactions (e.g. a sell can appear ABOVE the
    # buys that funded it, since it happened later in the day). Reversing
    # the raw row order — rather than sorting by date, which would lose
    # that same-day sequencing — recovers correct chronological order.
    trades.reverse()
    latest_balance = None
    if dated_balances:
        dated_balances.sort(key=lambda x: x[0])
        latest_balance = dated_balances[-1][1]

    return trades, latest_balance


def import_into_state(path: str) -> dict:
    trades, latest_balance = parse_fidelity_csv(path)

    day_trades_found = []
    unmatched_sells = []
    open_qty_tracker = {}

    for t in trades:
        sym = t["symbol"]
        if t["side"] == "BUY":
            open_qty_tracker[sym] = open_qty_tracker.get(sym, 0) + t["qty"]
        else:
            have = open_qty_tracker.get(sym, 0)
            if have <= 0:
                unmatched_sells.append({"date": t["date"].strftime("%Y-%m-%d"), "symbol": sym})
            open_qty_tracker[sym] = have - t["qty"]

        before_len = len(state_store.load().get("day_trade_timestamps", []))
        state_store.log_trade(sym, t["side"], t["qty"], t["price"], timestamp=t["date"])
        after_state = state_store.load()
        if len(after_state.get("day_trade_timestamps", [])) > before_len:
            day_trades_found.append({"date": t["date"].strftime("%Y-%m-%d"), "symbol": sym})

    return {
        "trades_imported": len(trades),
        "day_trades_found": day_trades_found,
        "unmatched_sells": unmatched_sells,
        "latest_cash_balance": latest_balance,
    }
