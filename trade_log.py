"""
CLI for keeping state.json accurate. Run this whenever your Fidelity
balance changes or you fill an order, so the risk engine's numbers are real.

Usage:
    python trade_log.py set-equity 12500
    python trade_log.py log-trade AAPL BUY 10 189.40
    python trade_log.py status
"""
import sys

import state_store


def cmd_set_equity(args):
    equity = float(args[0])
    state = state_store.set_equity(equity)
    print(f"Equity set to ${equity:,.2f} (peak: ${state['peak_equity']:,.2f})")


def cmd_log_trade(args):
    symbol, side, qty, price = args[0].upper(), args[1].upper(), float(args[2]), float(args[3])
    state_store.log_trade(symbol, side, qty, price)
    print(f"Logged {side} {qty} {symbol} @ ${price:.2f}")


def cmd_status(_args):
    state = state_store.load()
    day_trades = state_store.day_trade_count_last_5_sessions(state)
    print(f"Equity:            ${state['equity']:,.2f}")
    print(f"Peak equity:       ${state['peak_equity']:,.2f}")
    print(f"Daily P&L:         ${state['daily_pnl']:,.2f}")
    print(f"Day trades (~5d):  {day_trades}")
    print(f"Open positions:    {state['open_positions'] or '(none)'}")


COMMANDS = {
    "set-equity": cmd_set_equity,
    "log-trade": cmd_log_trade,
    "status": cmd_status,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
