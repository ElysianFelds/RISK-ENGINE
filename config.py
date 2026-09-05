"""
Central config. Edit these to match YOUR actual Fidelity account —
none of this is fetched automatically since Fidelity has no public API.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Data source keys (Alpaca is primary; others are fallbacks in priority order) ---
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
USE_ALPACA = bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
USE_FINNHUB = bool(FINNHUB_API_KEY)

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
USE_TWELVE_DATA = bool(TWELVE_DATA_API_KEY)

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
USE_ALPHA_VANTAGE = bool(ALPHA_VANTAGE_API_KEY)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
USE_POLYGON = bool(POLYGON_API_KEY)

TIINGO_API_KEY = os.getenv("TIINGO_API_KEY", "")
USE_TIINGO = bool(TIINGO_API_KEY)

FMP_API_KEY = os.getenv("FMP_API_KEY", "")
USE_FMP = bool(FMP_API_KEY)

# --- Optional email alerts on new signals ---
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
EMAIL_ENABLED = bool(EMAIL_ADDRESS and EMAIL_APP_PASSWORD and EMAIL_TO)

# Data source fallback order — first one with a key configured (and that
# successfully returns data) wins for each fetch. yfinance is always last
# since it needs no key.
DATA_SOURCE_PRIORITY = ["alpaca", "finnhub", "twelve_data", "alpha_vantage", "polygon", "tiingo", "yfinance"]

# Human-readable registry used by the "Set up API keys" menu — env var name,
# signup URL, and one-line note shown to the user.
API_KEY_REGISTRY = {
    "alpaca": {
        "label": "Alpaca (primary data + paper trading)",
        "env_vars": ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"],
        "signup_url": "https://alpaca.markets",
        "note": "Free real-time IEX feed + free paper trading. No funding required.",
    },
    "finnhub": {
        "label": "Finnhub",
        "env_vars": ["FINNHUB_API_KEY"],
        "signup_url": "https://finnhub.io/register",
        "note": "Free tier: real-time US stock quotes, ~60 calls/min.",
    },
    "twelve_data": {
        "label": "Twelve Data",
        "env_vars": ["TWELVE_DATA_API_KEY"],
        "signup_url": "https://twelvedata.com/pricing",
        "note": "Free tier: ~8 requests/min, 800/day, broad global coverage.",
    },
    "alpha_vantage": {
        "label": "Alpha Vantage",
        "env_vars": ["ALPHA_VANTAGE_API_KEY"],
        "signup_url": "https://www.alphavantage.co/support/#api-key",
        "note": "Free tier: low daily cap — verify current limits before relying on it.",
    },
    "polygon": {
        "label": "Polygon.io",
        "env_vars": ["POLYGON_API_KEY"],
        "signup_url": "https://polygon.io/dashboard/signup",
        "note": "Free tier: delayed data only, ~5 requests/min.",
    },
    "tiingo": {
        "label": "Tiingo",
        "env_vars": ["TIINGO_API_KEY"],
        "signup_url": "https://www.tiingo.com/account/api/token",
        "note": "Free tier: strong for EOD data, limited intraday.",
    },
    "fmp": {
        "label": "Financial Modeling Prep",
        "env_vars": ["FMP_API_KEY"],
        "signup_url": "https://site.financialmodelingprep.com/developer/docs",
        "note": "Free tier: limited daily calls; good for fundamentals alongside price data.",
    },
    "email_alerts": {
        "label": "Email alerts (optional — get emailed when a new signal fires)",
        "env_vars": ["EMAIL_ADDRESS", "EMAIL_APP_PASSWORD", "EMAIL_TO", "SMTP_SERVER", "SMTP_PORT"],
        "signup_url": "https://myaccount.google.com/apppasswords",
        "note": ("Uses SMTP. For Gmail: turn on 2-Step Verification, then generate an "
                  "App Password at the link above — your normal Gmail password will NOT "
                  "work here. SMTP_SERVER/SMTP_PORT can be left blank to default to Gmail; "
                  "set them explicitly if using Outlook/Yahoo/another provider."),
    },
}

# --- Account type (drives which risk rules apply) ---
# "margin"  -> PDT rule applies if equity < PDT_THRESHOLD
# "cash"    -> no PDT rule, but settlement / good-faith-violation risk applies
ACCOUNT_TYPE = os.getenv("ACCOUNT_TYPE", "margin")
PDT_THRESHOLD = 25_000.00
PDT_MAX_DAY_TRADES_PER_5_DAYS = 3

# --- Risk engine parameters (retail Fidelity account, NOT a prop-firm rule set) ---
RISK_PER_TRADE_PCT = 0.01          # risk 1% of equity per idea, sized off stop distance
MAX_DAILY_LOSS_PCT = 0.03          # stop generating new BUY/SELL signals after -3% on the day
MAX_DRAWDOWN_FROM_PEAK_PCT = 0.10  # pause signal generation if equity is 10% below its peak
MAX_POSITION_CONCENTRATION_PCT = 0.25  # no single symbol > 25% of equity
MAX_OPEN_POSITIONS = 5

# --- Strategy / regime parameters ---
ADX_TREND_THRESHOLD = 20      # ADX above this => trending regime
CHOP_WIDTH_PERCENTILE = 0.15  # today's BB width in the bottom 15% of ITS OWN recent range => choppy
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
ATR_STOP_MULTIPLIER = 1.5     # stop-loss = entry -/+ ATR * this
ATR_TARGET_MULTIPLIER = 2.5   # take-profit = entry -/+ ATR * this (>1.5 for positive R:R)

# --- Engine mechanics ---
BAR_TIMEFRAME_MINUTES = 15
LOOKBACK_BARS = 200
STATE_FILE = "state.json"
SIGNAL_LOG_CSV = "signals_log.csv"

# Market hours (US Eastern) — engine only actively pulls/generates inside this window
MARKET_OPEN = "09:30"
MARKET_CLOSE = "16:00"
MARKET_TZ = "America/New_York"

# ============================================================================
# Multi-layer signal engine (see quant_stock_signal_engine.md for the full
# architecture this section implements).
# ============================================================================

# --- §7 Relative Strength / §9 Regime — market/benchmark reference ---
BENCHMARK_SYMBOL = os.getenv("BENCHMARK_SYMBOL", "SPY")
# Optional per-symbol sector ETF for a sharper relative-strength comparison
# than the broad benchmark alone. Extend freely; anything not listed here
# just compares against BENCHMARK_SYMBOL.
SECTOR_ETF_MAP = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AMD": "XLK", "AVGO": "XLK",
    "CRM": "XLK", "ARM": "XLK", "SMCI": "XLK",
    "JPM": "XLF", "BAC": "XLF", "SOFI": "XLF",
    "XOM": "XLE", "CVX": "XLE",
    "META": "XLC", "GOOGL": "XLC", "NFLX": "XLC",
    "AMZN": "XLY", "TSLA": "XLY", "RIVN": "XLY",
}

# --- §4 Volatility engine ---
VOL_COMPRESSION_PERCENTILE = 0.15   # <= this percentile of own history -> "compression"
VOL_EXPANSION_PERCENTILE = 0.85     # >= this percentile of own history -> "expansion"

# --- §5 Volume engine ---
RVOL_STRONG_THRESHOLD = 2.0         # RVOL this many multiples of average saturates the volume score

# --- §8 Correlation engine (menu-driven research tool) ---
CORRELATION_LOOKBACK = 60           # bars

# --- §14 Signal Fusion — per-engine weights (need not sum to 1; normalized
# internally by total weight of engines that actually produced a score) ---
ENGINE_WEIGHTS = {
    "trend": 0.20,
    "momentum": 0.15,
    "mean_reversion": 0.10,
    "volume": 0.12,
    "structure": 0.15,
    "relative_strength": 0.13,
    "multi_timeframe": 0.10,
    "ml": 0.05,
}

# Composite-score thresholds mapping to STRONG LONG / LONG / WATCH / NEUTRAL
# / SHORT / STRONG SHORT (§14). Only |composite| >= "moderate" ever produces
# a BUY/SELL side; WATCH and NEUTRAL always resolve to HOLD.
COMPOSITE_THRESHOLDS = {
    "strong": 0.60,
    "moderate": 0.35,
    "watch": 0.15,
}

# --- §16 Anomaly / Event engine ---
ANOMALY_ZSCORE_THRESHOLD = 2.5
ANOMALY_RS_PCT_THRESHOLD = 3.0      # blended relative-strength %, see relative_strength_engine.py

# --- §11/§12/§20 Pattern research database & §13 ML layer ---
PATTERN_DB_PATH = os.getenv("PATTERN_DB_PATH", "pattern_db.sqlite")
ML_MODEL_PATH = os.getenv("ML_MODEL_PATH", "ml_model.pkl")
ML_MIN_TRAINING_ROWS = int(os.getenv("ML_MIN_TRAINING_ROWS", "200"))
