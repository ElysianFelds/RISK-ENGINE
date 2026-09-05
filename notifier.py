"""
Optional email alerts on new trade signals. Configure via menu option 8
(reuses the same API key setup flow — email is just another provider there).

Every email spells out not just the numbers but WHY the signal fired and
what closes it out, since a bare entry/stop/target doesn't tell you the
exit logic behind the strategy that generated it.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config

STRATEGY_EXPLANATIONS = {
    "trend_following": (
        "DOMINANT DRIVER: Trend / momentum\n"
        "The trend and/or momentum engines contributed the most to this "
        "signal — EMA9/21 alignment, price vs SMA50, ADX, and volatility-"
        "normalized multi-horizon returns all pointed the same direction. "
        "The bet is that the existing trend continues.\n\n"
        "SELL / EXIT CONDITIONS:\n"
        "  - Hit the STOP -> close the position. The trend read was wrong; get out.\n"
        "  - Hit the TARGET -> close the position. Take the profit.\n"
        "  - These are fixed ATR-based levels set when the signal fired — there is "
        "no automatic trailing stop; locking in more profit as price runs is a "
        "manual decision."
    ),
    "mean_reversion": (
        "DOMINANT DRIVER: Mean-reversion\n"
        "The mean-reversion engine contributed the most — price is at a "
        "statistically stretched z-score relative to its own recent mean, and "
        "the prevailing trend wasn't strong enough to override the fade. The "
        "bet is a bounce back toward the average, NOT a new sustained trend.\n\n"
        "SELL / EXIT CONDITIONS:\n"
        "  - Hit the TARGET -> close the position; the reversion played out.\n"
        "  - Hit the STOP -> close the position; the move kept extending against you.\n"
        "  - These trades tend to resolve faster than trend trades — don't expect "
        "this one to run for days."
    ),
    "breakout_structure": (
        "DOMINANT DRIVER: Market structure\n"
        "The structure engine contributed the most — a breakout, breakdown, or "
        "rejection against a reference level (prior day/week high-low, Donchian "
        "channel, or the opening range). Check whether this is a fresh breakout "
        "or an already-extended one (see the reasons list) before sizing up.\n\n"
        "SELL / EXIT CONDITIONS:\n"
        "  - Hit the STOP -> close the position; the level failed to hold.\n"
        "  - Hit the TARGET -> close the position; take the profit."
    ),
    "relative_strength": (
        "DOMINANT DRIVER: Relative strength\n"
        f"This symbol is moving meaningfully more (or less) than {config.BENCHMARK_SYMBOL} "
        "/ its sector ETF over the last several bars — a cross-sectional read, "
        "not a standalone price pattern.\n\n"
        "SELL / EXIT CONDITIONS:\n"
        "  - Hit the STOP -> close the position.\n"
        "  - Hit the TARGET -> close the position.\n"
        "  - Also worth watching: does the relative-strength edge persist, or "
        "does the stock start moving in line with the benchmark again?"
    ),
    "volume_driven": (
        "DOMINANT DRIVER: Volume\n"
        "Relative volume (RVOL) and OBV were the largest contributors — the "
        "move is backed by unusually heavy participation, not just price drift.\n\n"
        "SELL / EXIT CONDITIONS:\n"
        "  - Hit the STOP -> close the position.\n"
        "  - Hit the TARGET -> close the position.\n"
        "  - Watch for volume drying up before the target is hit; that's an early "
        "warning the move may be losing conviction."
    ),
    "ml_model": (
        "DOMINANT DRIVER: ML model\n"
        "The trained classifier's output was the largest contributor. It was "
        "trained on this engine's own historical feature/outcome log "
        "(pattern_db.sqlite) — treat it as one more vote, not an oracle, and "
        "check `python pattern_db.py research` periodically to see whether its "
        "edge is holding up out-of-sample.\n\n"
        "SELL / EXIT CONDITIONS:\n"
        "  - Hit the STOP -> close the position.\n"
        "  - Hit the TARGET -> close the position."
    ),
    "fusion": (
        "DOMINANT DRIVER: Blended (no single engine dominated)\n"
        "Several engines contributed roughly equally to this signal — see the "
        "reasons list in the alert above for the specific votes.\n\n"
        "SELL / EXIT CONDITIONS:\n"
        "  - Hit the STOP -> close the position.\n"
        "  - Hit the TARGET -> close the position."
    ),
}


def _build_subject(signals: list) -> str:
    parts = ", ".join(f"{r['side']} {r['symbol']}" for r in signals)
    return f"Signal Engine: {len(signals)} new signal(s) — {parts}"


def _build_body(signals: list) -> str:
    lines = [
        f"Signal Engine found {len(signals)} new trade idea(s).",
        "Nothing was placed — Fidelity has no trading API, so this is a suggestion",
        "for you to place manually and then log (menu option 5) once filled.",
        "=" * 72,
    ]
    for r in signals:
        lines.append("")
        lines.append(f"{r['side']} {r['suggested_qty']} shares of {r['symbol']}  "
                     f"[{r['signal_label']}, composite {r['composite_score']:+.2f}, "
                     f"confidence {r['confidence_pct']:.0f}%]")
        lines.append(f"  Entry:   ~${r['entry']}")
        lines.append(f"  Stop:     ${r['stop']}")
        lines.append(f"  Target:   ${r['target']}")
        lines.append(f"  Regime:   {r['regime']} / market {r.get('market_regime')} "
                     f"(ADX {r['adx']}, Bollinger width {r['bb_width_pct']}%)")
        lines.append(f"  Sizing:   {r['risk_reason']}")
        if r.get("reasons"):
            lines.append(f"  Reasons:  {'; '.join(r['reasons'])}")
        lines.append("")
        lines.append(STRATEGY_EXPLANATIONS.get(r["strategy"], "No strategy explanation available."))
        lines.append("")
        lines.append("-" * 72)
    lines.append("")
    lines.append("Reminder: log the fill in the menu (option 5) as soon as you place it —")
    lines.append("the risk engine's PDT count and sizing depend on that being current.")
    return "\n".join(lines)


def _send(subject: str, body: str) -> bool:
    if not config.EMAIL_ENABLED:
        return False
    msg = MIMEMultipart()
    msg["From"] = config.EMAIL_ADDRESS
    msg["To"] = config.EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(config.EMAIL_ADDRESS, config.EMAIL_APP_PASSWORD)
            server.sendmail(config.EMAIL_ADDRESS, config.EMAIL_TO, msg.as_string())
        return True
    except Exception as e:
        print(f"[notifier] Failed to send email: {e}")
        return False


def maybe_send(new_actionable: list):
    """Called from main.run_once() with only the genuinely NEW (not-yet-alerted)
    signals for this scan — silently does nothing if email isn't configured."""
    if not new_actionable or not config.EMAIL_ENABLED:
        return
    if _send(_build_subject(new_actionable), _build_body(new_actionable)):
        print(f"[notifier] Email sent to {config.EMAIL_TO}")


def send_test_email() -> bool:
    body = (
        "This is a test email from your Signal Engine setup.\n\n"
        "If you're reading this, email alerts are configured correctly and "
        "you'll get a message like this (with real trade details) whenever "
        "a new signal is found."
    )
    return _send("Signal Engine: test email", body)
