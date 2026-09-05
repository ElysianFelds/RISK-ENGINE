# Signal Engine — Fidelity Paper Trading Assistant

Automated market-data → signal → risk-checked "what to order" engine, built for
**manual execution on Fidelity** (Fidelity has no public trading API, so this
tool never places real orders for you — it tells you exactly what to do and
you click the button yourself).

Alpaca is used only as a **free, real, paper-trading data + simulation backend**
so you can automate the boring part (watch the market, run the math) and
sanity-check the strategy logic against real fills before you ever risk a
dollar at Fidelity.

```
Market data (Alpaca / yfinance) + Benchmark (SPY)
        │
        ▼
  Feature Engine (candle, momentum, volatility, volume, structure)
        │
        ▼
  Regime Detector (per-symbol: trending/ranging/choppy
                    market-wide: TRENDING_BULL/BEAR, PANIC, BREAKOUT, ...)
        │
        ▼
  Signal Models — each votes a score in [-1, +1]:
    momentum/trend · mean-reversion · volatility · volume/liquidity
    market structure · relative strength vs benchmark · multi-timeframe
    alignment · (optional) trained ML model
        │
        ▼
  Signal Fusion → composite score, STRONG LONG..STRONG SHORT label, confidence %
        │
        ▼
  Risk Engine (Fidelity rules: PDT, position sizing, daily loss, drawdown)
        │
        ▼
  Console + CSV log + pattern research DB  →  YOU place the order  →  you log the fill
```

This implements the multi-layer architecture described in
`quant_stock_signal_engine.md` (§1-§20) — see that file for the full
research rationale behind each layer. Section numbers below (§N) refer to it.

## 1. Setup

**If you're on Ubuntu/WSL:** `python3` and `pip3` are usually pre-installed;
if not, `sudo apt update && sudo apt install python3 python3-pip python3-venv`.
Everything below runs the same as native Linux.

```bash
python3 -m venv venv
source venv/bin/activate        # Windows (native, not WSL): venv\Scripts\activate
pip install -r requirements.txt
```

Get **free Alpaca paper keys** (2 minutes, no funding required):
1. Sign up at https://alpaca.markets (paper-only accounts are free and instant)
2. Dashboard → "View API Keys" → generate paper key/secret
3. Either paste them into `.env` directly, or just launch the menu and use
   **option 8 (Set up API keys)** — same result, no file editing needed.

If you skip this, the engine automatically falls back to `yfinance`
(no key needed) for data-only mode — you lose Alpaca's simulated paper
fills but signal generation still works. Option 8 also lets you add any of
the other free providers listed in section 6 as extra fallbacks, all at once.

## 2. Run it — everything is menu-driven, no commands to remember

**Ubuntu/WSL or Mac/Linux:** `./risk-engine.sh` from inside the folder
(or double-click it in the WSL file explorer path `\\wsl$\...`).
**Windows (native):** double-click `risk-engine.bat`.

Either way you land on a numbered menu:

```
  1. Run one signal scan now
  2. Watch continuously (auto-scan on an interval)
  3. View account & risk status
  4. Set account equity
  5. Log a trade fill
  6. Edit watchlist
  7. View current risk config
  8. Set up API keys
  9. Import Fidelity trade history (CSV)
  10. Correlation & relative-strength dashboard
  11. Pattern research (edge stats & IC on logged history)
  12. Train / update ML model
  13. Help — detailed instructions for every option
  0. Exit
```

**First time setup, in order:**
1. Option **8** — add your free Alpaca keys (and any other providers you
   want as backup — Finnhub, Twelve Data, Alpha Vantage, Polygon, Tiingo,
   Financial Modeling Prep). You can set up as many as you like; the engine
   tries them in priority order and falls back automatically.
2. Option **4** — enter your current Fidelity account value. This is what
   the risk engine sizes and gates everything against.
3. Option **6** — enter your watchlist (comma-separated tickers). It's saved
   so you don't re-type it every time.

        #Sample list# AAPL, MSFT, SPY, QQQ, NVDA, TSLA, AMD, GOOGL, AMZN, META, AEMD, CAPR, MOVE, SSM, AVGO, NFLX, PLTR, CRM, COIN, MSTR, SMCI, ARM, SOFI, RIVN, XLK, XLF, XLE, SMH, IWM, INTC, MU, JPM, BAC, WMT, COST, ORCL, UBER, IONQ, TSM, LLY, XOM, HOOD
   
5. Option **1** or **2** — run a scan, or start continuous watching.

Forgot how something works? **Option 13** walks through every menu item and
the key concepts (regime, signal fusion, risk status) in plain English.

**Every time you place a trade at Fidelity:** come back and use option
**5** to log the fill (symbol, side, quantity, price). This is what keeps
the PDT count and daily-loss numbers accurate — there's no Fidelity feed
to fall back on, so the engine is only as good as what you log here.

### Want to type a word instead of double-clicking?
**Ubuntu/WSL or Mac/Linux:** add this line to `~/.bashrc` (WSL/Ubuntu) or
`~/.zshrc` (Mac) — replace the path with wherever you unzipped this folder,
e.g. `/home/<you>/algo_signal_engine` in WSL:
```bash
alias risk-engine="cd /path/to/algo_signal_engine && ./risk-engine.sh"
```
Then `source ~/.bashrc` (or open a new terminal) and just type `risk-engine`
from anywhere.

**Windows:** put `algo_signal_engine` on your PATH (System Properties →
Environment Variables → Path), then typing `risk-engine.bat` from any
Command Prompt window launches it.

### If you'd rather use raw commands
Everything the menu does is also available directly — `python main.py
--watchlist AAPL,MSFT --once` for a single scan, `python trade_log.py
set-equity 12500` / `log-trade AAPL BUY 10 189.40` / `status` for account
state. The menu just wraps these so you never have to type them.

## 3. Files

| File | Purpose |
|---|---|
| `menu.py` | **Start here.** Interactive menu (with ASCII banner) wrapping everything below |
| `risk-engine.sh` / `risk-engine.bat` | Double-clickable launchers for the menu |
| `env_setup.py` | Reads/writes `.env` and hot-reloads config — powers menu option 8 |
| `data_fetcher.py` | Pulls bars from Alpaca, Finnhub, Twelve Data, Alpha Vantage, Polygon, Tiingo, or yfinance — whichever configured provider responds first, in that priority order |
| `indicators.py` | Low-level feature library: SMA/EMA/RSI/BB/ATR/ADX plus §1/§2/§4/§5 additions — candle-body/wick ratios, regression slope/R², Donchian channel, realized/Parkinson/Garman-Klass/Yang-Zhang volatility, OBV, session VWAP, RVOL |
| `candle_features.py` | §1/§11 candle pattern labeling (engulfing, doji, hammer, marubozu, inside/outside bar) and HH/HL/LH/LL swing structure — labels only, never a hardcoded BUY/SELL |
| `momentum_engine.py` | §2 multi-horizon volatility-normalized momentum (M1..M252) + trend score (EMA alignment, ADX, regression R²) |
| `mean_reversion_engine.py` | §3 z-score vs rolling mean, damped by prevailing trend strength so it doesn't blindly fade a strong trend |
| `volatility_engine.py` | §4 four volatility estimators + compression/expansion state + a confidence multiplier signal_fusion uses to scale conviction |
| `volume_engine.py` | §5 RVOL, OBV slope, VWAP distance, price-volume divergence detection |
| `structure_engine.py` | §6 prior day/week high-low, opening range, Donchian breakout/breakdown/failed-breakout/retest classification |
| `relative_strength_engine.py` | §7 multi-horizon return vs benchmark (or sector ETF, see `config.SECTOR_ETF_MAP`) |
| `correlation_engine.py` | §8 pairwise correlation matrix across the scanned universe + breakdown/unusual-correlation flags + beta-hedged pair-spread z-score (menu option 10) |
| `regime.py` | §9 per-symbol trending/ranging/choppy classifier **and** market-wide regime (TRENDING_BULL/BEAR, LOW/HIGH_VOL_RANGE, BREAKOUT, PANIC, RECOVERY) from the benchmark |
| `multi_timeframe.py` | §10 daily-timeframe trend read (via yfinance) blended with the primary intraday timeframe into a trend-alignment score |
| `anomaly_engine.py` | §16 z-score based anomaly flags on return/range/volume/volatility/relative-strength — informational, not directional |
| `pattern_db.py` | §11/§12/§20 SQLite research log: every scan is one labeled observation; backfills forward returns and reports pattern/regime edge stats + Information Coefficient (menu option 11) |
| `ml_model.py` | §13 optional logistic-regression/gradient-boosting classifier trained on `pattern_db`'s labeled history (menu option 12); degrades to a neutral vote if scikit-learn isn't installed or there's not enough data yet |
| `signal_fusion.py` | §14 combines every engine's [-1,+1] score into one weighted composite, scaled by volatility/regime confidence, mapped to STRONG LONG..STRONG SHORT + confidence % + plain-English reasons |
| `strategies.py` | Execution layer: turns the fused side into ATR-based entry/stop/target, and labels the dominant driver for the notifier's explanation |
| `risk_engine.py` | §15 Fidelity-appropriate rules — kept deliberately separate from the alpha/signal layers above (see below) |
| `signal_engine.py` | Orchestrates the full pipeline for one symbol (§17 architecture) and logs the result to `pattern_db` |
| `main.py` | Watchlist loop, market-hours check, benchmark fetch, console output, CSV logging |
| `trade_log.py` | Raw CLI equivalent of the menu's equity/trade-logging options |
| `state.json` | Your account equity, peak equity, day-trade timestamps, trade log (auto-created) |
| `watchlist.json` | Your saved watchlist (auto-created via menu option 6) |
| `pattern_db.sqlite` | Research log of every scanned observation (auto-created) |
| `ml_model.pkl` | Trained ML model, if you've run menu option 12 (auto-created) |

## 4. Signal fusion — how a composite score actually gets made

No single indicator ever triggers a BUY/SELL by itself (§14). Each engine
above computes a score in `[-1, +1]`; `signal_fusion.py` combines them as:

```
composite = clip(
    sum(weight_i * score_i) / sum(|weight_i| for engines that reported)
    * volatility_confidence_multiplier
    * market_regime_confidence_multiplier
)
```

Weights live in `config.ENGINE_WEIGHTS`; thresholds mapping the composite to
`STRONG LONG / LONG / WATCH / NEUTRAL / SHORT / STRONG SHORT` live in
`config.COMPOSITE_THRESHOLDS`. Only `LONG`/`STRONG LONG`/`SHORT`/`STRONG SHORT`
ever produce a tradeable side (`BUY`/`SELL`) — `WATCH` and `NEUTRAL` are
always `HOLD`. The risk engine (§15) never sees or adjusts this score; it
only gates and sizes whatever side/entry/stop it's handed, per the doc's
explicit "keep alpha separate from risk."

## 5. Pattern research & the statistical foundation (§11/§12/§19/§20)

Every scan logs one observation per symbol to `pattern_db.sqlite`: the
candle pattern, swing structure, regime, and every engine's score at that
moment. Once enough time has passed for the +1/+5/+10/+20-bar forward
returns to actually exist, **menu option 11** backfills them and reports,
per pattern and per regime, the sample size, average forward return, win
rate, and a simple Sharpe-like ratio — plus the Information Coefficient
(correlation with future returns) for each continuous engine score. This is
deliberately separate from live scanning: it's how you find out, empirically,
whether a given feature or pattern is actually worth listening to, and
under what conditions — the doc's central point that indicator counting is
not the goal, out-of-sample predictive validity is.

**Menu option 12** trains an optional ML classifier (§13) on that same
labeled history, using the identical engine-score features you already see
in the scan table — added only after the statistical foundation exists, and
treated as one more vote in signal fusion, never a black box overriding it.

## 6. Risk rules implemented (Fidelity, not prop-firm)

| Rule | Why it matters at Fidelity |
|---|---|
| **PDT rule** | If equity < $25,000 in a margin account, you're limited to 3 day trades per rolling 5 business days — the 4th gets you flagged/frozen. The engine counts your logged day trades and **blocks** new day-trade signals once you're at the limit. Cash accounts skip PDT but face T+1 settlement — the engine flags that too. |
| **Position sizing** | Risk-per-trade % of *your actual equity* (from `state.json`), sized off ATR-based stop distance — not a flat share count. |
| **Max daily loss** | Halts new signals for the rest of the day once your logged daily loss hits your threshold. |
| **Max drawdown from peak** | Pauses signal generation if equity falls a set % below its recorded peak, until you reset. |
| **Max concentration** | Caps how much of your account one symbol/position can represent. |
| **Max open positions** | Simple cap on simultaneous ideas so you're not tracking 15 fills by hand. |

None of these are prop-firm trailing-drawdown or consistency-rule constructs —
they're retail-account constructs specific to a self-directed Fidelity
account. Edit the numbers in `config.py` to match your actual account type
and size.

## 7. Free market-data APIs — set up any of these via menu option 8

| Provider | Free tier | Key needed | Notes |
|---|---|---|---|
| **Alpaca Market Data** | 200 requests per minute, Real-time IEX feed, ~7 yrs history, generous rate limit | Yes (free) | Used by this project. IEX ≈ 2% of consolidated volume — fine for signals, not for large/illiquid names. |
| **yfinance (Yahoo Finance)** | Delayed/EOD + decent intraday | No | Unofficial wrapper around Yahoo's endpoints; free but no SLA, can break/rate-limit without notice. Used here as the no-key fallback. |
| **Finnhub** | Real-time US stock quotes, 60 calls/min | Yes (free) | Good secondary quote source. |
| **Twelve Data** | 8 req/min, 800/day | Yes (free) | Broad global coverage, simple REST. |
| **Alpha Vantage** | 5 req/min, 25/day (current limits — verify) | Yes (free) | Good for indicators-as-a-service, but low daily cap for polling loops. |
| **Polygon.io** | Delayed data, 5 req/min | Yes (free) | Real-time/full history requires paid tier. |
| **Tiingo** | 50 requests/hour (1,000 daily) EOD + limited intraday | Yes (free) | Strong for EOD backtesting datasets. |
| **Financial Modeling Prep** | Limited daily calls | Yes (free) | Good for fundamentals alongside price data. |
| Google Finance | No public API | — | `GOOGLEFINANCE()` only works inside Google Sheets, not callable from a script. |
| Marketstack | 100 requests per month | reset API | Simple data queries or basic widgets |




