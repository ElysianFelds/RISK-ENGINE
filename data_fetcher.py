"""
Pulls recent bars for a symbol, trying each configured provider in priority
order until one returns data. Providers with no key set are skipped
automatically. yfinance is always last since it needs no key.

Order (config.DATA_SOURCE_PRIORITY): alpaca, finnhub, twelve_data,
alpha_vantage, polygon, tiingo, yfinance.
"""
import concurrent.futures

import pandas as pd
import requests

import config

_STD_COLS = ["Open", "High", "Low", "Close", "Volume"]


def _fetch_alpaca(symbol: str, timeframe_minutes: int, lookback_bars: int) -> pd.DataFrame:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)
    tf = TimeFrame(timeframe_minutes, TimeFrame.Unit.Minute) if timeframe_minutes != 1 else TimeFrame.Minute

    req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, limit=lookback_bars)
    bars = client.get_stock_bars(req).df
    if bars.empty:
        return pd.DataFrame()
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol, level=0)
    bars = bars.rename(columns={
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
    })
    return bars[_STD_COLS]


def _fetch_finnhub(symbol: str, timeframe_minutes: int, lookback_bars: int) -> pd.DataFrame:
    import time
    resolution_map = {1: "1", 5: "5", 15: "15", 30: "30", 60: "60"}
    resolution = resolution_map.get(timeframe_minutes, "15")
    seconds_per_bar = timeframe_minutes * 60
    to_ts = int(time.time())
    from_ts = to_ts - seconds_per_bar * lookback_bars

    resp = requests.get(
        "https://finnhub.io/api/v1/stock/candle",
        params={"symbol": symbol, "resolution": resolution, "from": from_ts,
                "to": to_ts, "token": config.FINNHUB_API_KEY},
        timeout=10,
    )
    data = resp.json()
    if data.get("s") != "ok":
        return pd.DataFrame()
    df = pd.DataFrame({
        "Open": data["o"], "High": data["h"], "Low": data["l"],
        "Close": data["c"], "Volume": data["v"],
    }, index=pd.to_datetime(data["t"], unit="s"))
    return df


def _fetch_twelve_data(symbol: str, timeframe_minutes: int, lookback_bars: int) -> pd.DataFrame:
    interval_map = {1: "1min", 5: "5min", 15: "15min", 30: "30min", 60: "1h"}
    interval = interval_map.get(timeframe_minutes, "15min")

    resp = requests.get(
        "https://api.twelvedata.com/time_series",
        params={"symbol": symbol, "interval": interval, "outputsize": lookback_bars,
                "apikey": config.TWELVE_DATA_API_KEY},
        timeout=10,
    )
    data = resp.json()
    values = data.get("values")
    if not values:
        return pd.DataFrame()
    df = pd.DataFrame(values)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                             "close": "Close", "volume": "Volume"})
    for col in _STD_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[_STD_COLS]


def _fetch_alpha_vantage(symbol: str, timeframe_minutes: int, lookback_bars: int) -> pd.DataFrame:
    interval_map = {1: "1min", 5: "5min", 15: "15min", 30: "30min", 60: "60min"}
    interval = interval_map.get(timeframe_minutes, "15min")

    resp = requests.get(
        "https://www.alphavantage.co/query",
        params={"function": "TIME_SERIES_INTRADAY", "symbol": symbol, "interval": interval,
                "outputsize": "compact", "apikey": config.ALPHA_VANTAGE_API_KEY},
        timeout=10,
    )
    data = resp.json()
    key = f"Time Series ({interval})"
    series = data.get(key)
    if not series:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(series, orient="index")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df.rename(columns={
        "1. open": "Open", "2. high": "High", "3. low": "Low",
        "4. close": "Close", "5. volume": "Volume",
    })
    for col in _STD_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[_STD_COLS].tail(lookback_bars)


def _fetch_polygon(symbol: str, timeframe_minutes: int, lookback_bars: int) -> pd.DataFrame:
    from datetime import datetime, timedelta
    end = datetime.utcnow()
    start = end - timedelta(days=max(5, lookback_bars * timeframe_minutes // (60 * 6)))
    resp = requests.get(
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{timeframe_minutes}/minute/"
        f"{start.date()}/{end.date()}",
        params={"adjusted": "true", "sort": "asc", "limit": lookback_bars,
                "apiKey": config.POLYGON_API_KEY},
        timeout=10,
    )
    data = resp.json()
    results = data.get("results")
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    df.index = pd.to_datetime(df["t"], unit="ms")
    df = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    return df[_STD_COLS].tail(lookback_bars)


def _fetch_tiingo(symbol: str, timeframe_minutes: int, lookback_bars: int) -> pd.DataFrame:
    from datetime import datetime, timedelta
    start = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    resp = requests.get(
        f"https://api.tiingo.com/iex/{symbol}/prices",
        params={"startDate": start, "resampleFreq": f"{timeframe_minutes}min",
                "token": config.TIINGO_API_KEY},
        timeout=10,
    )
    data = resp.json()
    if not isinstance(data, list) or not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df.index = pd.to_datetime(df["date"])
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                             "close": "Close", "volume": "Volume"})
    return df[_STD_COLS].tail(lookback_bars)


def _fetch_yfinance(symbol: str, timeframe_minutes: int, lookback_bars: int) -> pd.DataFrame:
    import yfinance as yf
    interval_map = {1: "1m", 5: "5m", 15: "15m", 30: "30m", 60: "60m"}
    interval = interval_map.get(timeframe_minutes, "15m")
    period = "5d" if interval in ("1m", "5m") else "60d"

    df = yf.download(symbol, period=period, interval=interval, progress=False,
                      auto_adjust=True, timeout=10)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.tail(lookback_bars)[_STD_COLS]


_PROVIDER_FUNCS = {
    "alpaca": (_fetch_alpaca, lambda: config.USE_ALPACA),
    "finnhub": (_fetch_finnhub, lambda: config.USE_FINNHUB),
    "twelve_data": (_fetch_twelve_data, lambda: config.USE_TWELVE_DATA),
    "alpha_vantage": (_fetch_alpha_vantage, lambda: config.USE_ALPHA_VANTAGE),
    "polygon": (_fetch_polygon, lambda: config.USE_POLYGON),
    "tiingo": (_fetch_tiingo, lambda: config.USE_TIINGO),
    "yfinance": (_fetch_yfinance, lambda: True),
}


def get_bars(symbol: str, timeframe_minutes: int = None, lookback_bars: int = None,
             verbose: bool = False, timeout_seconds: int = 15) -> pd.DataFrame:
    """Tries each configured provider in config.DATA_SOURCE_PRIORITY order.
    Each provider call is wrapped in a hard timeout so a single slow/hung
    provider (e.g. an obscure ticker Yahoo stalls on) can never freeze the
    whole scan — it just gets skipped and the next provider is tried."""
    timeframe_minutes = timeframe_minutes or config.BAR_TIMEFRAME_MINUTES
    lookback_bars = lookback_bars or config.LOOKBACK_BARS

    for name in config.DATA_SOURCE_PRIORITY:
        fetch_fn, is_configured = _PROVIDER_FUNCS[name]
        if not is_configured():
            continue
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(fetch_fn, symbol, timeframe_minutes, lookback_bars)
        try:
            df = future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            print(f"[data_fetcher] {name} timed out for {symbol} after {timeout_seconds}s; trying next source.")
            executor.shutdown(wait=False)
            continue
        except Exception as e:
            if verbose:
                print(f"[data_fetcher] {name} failed for {symbol} ({e}); trying next source.")
            executor.shutdown(wait=False)
            continue

        executor.shutdown(wait=False)
        if not df.empty:
            if verbose:
                print(f"[data_fetcher] {symbol}: served by {name}")
            return df

    return pd.DataFrame()


def active_sources() -> list:
    """Returns the ordered list of providers that currently have keys configured."""
    return [name for name in config.DATA_SOURCE_PRIORITY if _PROVIDER_FUNCS[name][1]()]
