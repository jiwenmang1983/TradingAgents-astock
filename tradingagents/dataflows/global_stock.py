"""Global stock data (HK/US) vendor for TradingAgents.

Zero third-party data dependency. All sources are direct HTTP APIs.

Data sources:
- HK realtime quote: Tencent qt.gtimg.cn (r_hkXXXXX)
- HK K-line: Yahoo Finance chart API
- US realtime quote: Sina hq.sinajs.cn (gb_ticker)
- US K-line: Sina stock.finance.sina.com.cn
- Financial statements: Eastmoney datacenter
- News: Yahoo Finance search
"""

from __future__ import annotations

from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import re
import urllib.request
from typing import Annotated, Literal

import pandas as pd
import requests

from .utils import safe_ticker_component


_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


# ---------------------------------------------------------------------------
# Market detection
# ---------------------------------------------------------------------------

def _detect_market(symbol: str) -> Literal["hk", "us", "astock"]:
    """Detect market from ticker format."""
    s = symbol.strip().upper()
    if s.endswith(".HK"):
        return "hk"
    if s.endswith(".O") or s.endswith(".N"):
        return "us"
    if s.endswith(".SS") or s.endswith(".SZ"):
        return "astock"
    if s.isdigit():
        if len(s) == 6:
            return "astock"
        if len(s) in (4, 5):
            return "hk"
    if s.isalpha():
        return "us"
    return "astock"


def _normalize_symbol(symbol: str) -> tuple[str, str, str]:
    """Normalize symbol to (yahoo_code, tencent_code, market).

    Yahoo Finance HK uses 4-digit codes (0700.HK).
    Tencent qt.gtimg.cn HK uses 5-digit codes (00700).
    US uses ticker symbol (AAPL).
    A-stock uses 6-digit code (600000).
    """
    s = symbol.strip()
    market = _detect_market(s)

    if market == "hk":
        raw = s.split(".")[0].strip()
        int_val = int(raw)  # removes leading zeros
        tencent_code = str(int_val).zfill(5)
        yahoo_code = str(int_val).zfill(4)
        return yahoo_code, tencent_code, "hk"

    if market == "us":
        return s.upper(), s.upper(), "us"

    # astock — strip .SS/.SZ
    for suffix in (".SS", ".SZ", ".BJ"):
        if s.upper().endswith(suffix):
            s = s[: -len(suffix)]
            break
    for prefix in ("SH", "SZ", "BJ"):
        if s.upper().startswith(prefix):
            s = s[len(prefix):]
            break
    return s.strip(), s.strip(), "astock"


# ---------------------------------------------------------------------------
# HK quote (Tencent qt.gtimg.cn)
# ---------------------------------------------------------------------------

def _hk_quote(code: str) -> dict:
    """Get HK real-time quote from Tencent qt.gtimg.cn."""
    url = f"https://qt.gtimg.cn/q=r_hk{code}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")
    m = re.search(r'"(.+)"', raw)
    if not m:
        return {}
    fields = m.group(1).split("~")
    if len(fields) < 50:
        return {}
    try:
        return {
            "name": fields[1],
            "price": float(fields[3]) if fields[3] else 0,
            "prev_close": float(fields[4]) if fields[4] else 0,
            "open": float(fields[5]) if fields[5] else 0,
            "volume": float(fields[6]) if fields[6] else 0,
            "amount": float(fields[37]) if fields[37] else 0,
            "high": float(fields[33]) if fields[33] else 0,
            "low": float(fields[34]) if fields[34] else 0,
            "high_52w": float(fields[35]) if fields[35] else 0,
            "low_52w": float(fields[36]) if fields[36] else 0,
            "change_pct": float(fields[32]) if fields[32] else 0,
            "pe": float(fields[39]) if fields[39] else 0,
            "pb": float(fields[56]) if fields[56] else 0,
            "market_cap": float(fields[44]) if fields[44] else 0,
        }
    except (ValueError, IndexError):
        return {}


# ---------------------------------------------------------------------------
# US quote (Sina hq.sinajs.cn)
# ---------------------------------------------------------------------------

def _us_quote(ticker: str) -> dict:
    """Get US real-time quote from Sina hq.sinajs.cn."""
    url = f"https://hq.sinajs.cn/list=gb_{ticker.lower()}"
    req = urllib.request.Request(url)
    req.add_header("Referer", "https://finance.sina.com.cn/")
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    resp = requests.get(url, headers={"Referer": "https://finance.sina.com.cn/", "User-Agent": _UA}, timeout=10)
    resp.encoding = "gbk"
    m = re.search(r'"(.+)"', resp.text)
    if not m:
        return {}
    fields = m.group(1).split(",")
    if len(fields) < 30:
        return {}
    try:
        return {
            "name": fields[0],
            "price": float(fields[1]) if fields[1] else 0,
            "change_pct": float(fields[2]) if fields[2] else 0,
            "open": float(fields[5]) if fields[5] else 0,
            "high": float(fields[6]) if fields[6] else 0,
            "low": float(fields[7]) if fields[7] else 0,
            "volume": float(fields[10]) if fields[10] else 0,
            "high_52w": float(fields[8]) if fields[8] else 0,
            "low_52w": float(fields[9]) if fields[9] else 0,
            "market_cap": float(fields[12]) if fields[12] else 0,
            "eps": float(fields[13]) if fields[13] else 0,
            "pe": float(fields[14]) if fields[14] else 0,
            "prev_close": float(fields[26]) if fields[26] else 0,
        }
    except (ValueError, IndexError):
        return {}


# ---------------------------------------------------------------------------
# Yahoo Finance K-line
# ---------------------------------------------------------------------------

def _eastmoney_kline(secid: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch K-line from Eastmoney push2his API (US/HK fallback)."""
    # secid format: 116.00700 (HK), 105.BABA (US)
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56",
        "klt": "101",  # Daily
        "fqt": "1",    # Forward-adjusted
        "beg": start_date.replace("-", ""),
        "end": end_date.replace("-", ""),
    }
    headers = {"User-Agent": _UA, "Referer": "https://finance.eastmoney.com/"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    if r.status_code != 200:
        return pd.DataFrame()
    d = r.json()
    klines = d.get("data", {}).get("klines", [])
    rows = []
    for kl in klines:
        fields = kl.split(",")
        if len(fields) < 6:
            continue
        rows.append({
            "Date": fields[0],
            "Open": float(fields[1]) if fields[1] else None,
            "High": float(fields[2]) if fields[2] else None,
            "Low": float(fields[3]) if fields[3] else None,
            "Close": float(fields[4]) if fields[4] else None,
            "Volume": float(fields[5]) if fields[5] else 0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").dropna(subset=["Close"])


def _tencent_kline(tencent_code: str, num: int = 60) -> pd.DataFrame:
    """Fetch HK K-line from Tencent (fallback when Yahoo is rate-limited)."""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"_var": "kline_dayhfq", "param": f"hk{tencent_code},day,,,{num},qfq"}
    headers = {"User-Agent": _UA}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    text = r.text
    m = re.search(r"=(.+)$", text)
    if not m:
        return pd.DataFrame()
    d = json.loads(m.group(1))
    days = d.get("data", {}).get(f"hk{tencent_code}", {}).get("day", [])
    rows = []
    for day in days:
        if len(day) < 6:
            continue
        rows.append({
            "Date": day[0],
            "Open": float(day[1]) if day[1] else None,
            "High": float(day[2]) if day[2] else None,
            "Low": float(day[3]) if day[3] else None,
            "Close": float(day[4]) if day[4] else None,
            "Volume": float(day[5]) if day[5] else 0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").dropna(subset=["Close"])


def _fetch_with_retry(url: str, params: dict, headers: dict, max_retries: int = 3) -> requests.Response:
    """Fetch URL with retry on rate limit (429)."""
    for attempt in range(max_retries):
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code != 429:
            return r
        wait = 2 ** attempt
        print(f"Yahoo Finance rate limited, retrying in {wait}s (attempt {attempt+1}/{max_retries})")
        import time; time.sleep(wait)
    return requests.get(url, params=params, headers=headers, timeout=15)


def _yahoo_kline(symbol: str, range_: str = "6mo") -> pd.DataFrame:
    """Fetch OHLCV from Yahoo Finance chart API (falls back to Tencent for HK)."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": range_}
    headers = {"User-Agent": _UA}
    r = _fetch_with_retry(url, params, headers)
    if r.status_code in (429, 403):
        # Fallback to Tencent for HK stocks (Tencent has 2+ years history)
        m = re.match(r"(\d+)\.HK", symbol, re.IGNORECASE)
        if m:
            tencent_code = m.group(1).zfill(5)
            return _tencent_kline(tencent_code, num=500)
        r.raise_for_status()
    r.raise_for_status()
    d = r.json()
    chart = d.get("chart", {}).get("result", [{}])[0]
    timestamps = chart.get("timestamp", [])
    quote = chart.get("indicators", {}).get("quote", [{}])[0]

    rows = []
    for i, ts in enumerate(timestamps):
        rows.append({
            "Date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
            "Open": round(quote["open"][i], 2) if quote["open"][i] else None,
            "High": round(quote["high"][i], 2) if quote["high"][i] else None,
            "Low": round(quote["low"][i], 2) if quote["low"][i] else None,
            "Close": round(quote["close"][i], 2) if quote["close"][i] else None,
            "Volume": int(quote["volume"][i]) if quote["volume"][i] else 0,
        })
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return df.dropna(subset=["Close"])


# ---------------------------------------------------------------------------
# Yahoo US K-line
# ---------------------------------------------------------------------------

def _yahoo_us_kline(ticker: str, range_: str = "2y") -> pd.DataFrame:
    """Fetch US daily K-line from Yahoo Finance."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"interval": "1d", "range": range_}
    headers = {"User-Agent": _UA}
    r = _fetch_with_retry(url, params, headers)
    r.raise_for_status()
    d = r.json()
    chart = d.get("chart", {}).get("result", [{}])[0]
    timestamps = chart.get("timestamp", [])
    quote = chart.get("indicators", {}).get("quote", [{}])[0]

    rows = []
    for i, ts in enumerate(timestamps):
        rows.append({
            "Date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
            "Open": round(quote["open"][i], 2) if quote["open"][i] else None,
            "High": round(quote["high"][i], 2) if quote["high"][i] else None,
            "Low": round(quote["low"][i], 2) if quote["low"][i] else None,
            "Close": round(quote["close"][i], 2) if quote["close"][i] else None,
            "Volume": int(quote["volume"][i]) if quote["volume"][i] else 0,
        })
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    return df.dropna(subset=["Close"])


def _sina_us_kline(ticker: str, num: int = 120) -> pd.DataFrame:
    """Fetch US daily K-line from Sina (returns data back to 1984)."""
    url = "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var/US_MinKService.getDailyK"
    params = {"symbol": ticker.upper(), "num": num}
    headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": _UA}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    if r.status_code != 200:
        return pd.DataFrame()
    # Response: var([{"d":"1984-09-07","o":"26.50",...}])
    m = re.search(r"\((.+)\)", r.text, re.DOTALL)
    if not m:
        return pd.DataFrame()
    try:
        items = json.loads(m.group(1))
    except json.JSONDecodeError:
        return pd.DataFrame()
    rows = []
    for it in items:
        rows.append({
            "Date": it.get("d"),
            "Open": float(it["o"]) if it.get("o") else None,
            "High": float(it["h"]) if it.get("h") else None,
            "Low": float(it["l"]) if it.get("l") else None,
            "Close": float(it["c"]) if it.get("c") else None,
            "Volume": int(it["v"]) if it.get("v") else 0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"])
    return df.set_index("Date").dropna(subset=["Close"])


# ---------------------------------------------------------------------------
# Eastmoney datacenter helper
# ---------------------------------------------------------------------------

def _em_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
) -> list[dict]:
    """Query Eastmoney datacenter for HK/US financial data."""
    params = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    r = requests.get(_DATACENTER_URL, params=params, headers={"User-Agent": _UA}, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


# ---------------------------------------------------------------------------
# Technical indicator calculation
# ---------------------------------------------------------------------------

def _calc_ema(values: list[float], period: int) -> list[float]:
    result = [values[0]]
    k = 2 / (period + 1)
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _calc_indicators(df: pd.DataFrame, ticker: str) -> dict:
    """Calculate MA/MACD/RSI/KDJ/Bollinger from OHLCV DataFrame."""
    closes = df["Close"].tolist()
    highs = df["High"].tolist()
    lows = df["Low"].tolist()
    n = len(closes)

    # MA
    ma_rows = []
    for i in range(n):
        row = {"date": str(df.index[i])[:10], "close": closes[i]}
        for p in [5, 10, 20, 60]:
            if i >= p - 1:
                row[f"ma{p}"] = round(sum(closes[i - p + 1:i + 1]) / p, 2)
        ma_rows.append(row)

    # EMA + MACD
    ema12 = _calc_ema(closes, 12)
    ema26 = _calc_ema(closes, 26)
    dif = [f - s for f, s in zip(ema12, ema26)]
    dea = _calc_ema(dif, 9)
    macd_rows = [{
        "date": str(df.index[i])[:10],
        "close": closes[i],
        "dif": round(dif[i], 4),
        "dea": round(dea[i], 4),
        "macd_hist": round((dif[i] - dea[i]) * 2, 4),
    } for i in range(n)]

    # RSI
    changes = [0.0] + [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]
    rsi_rows = []
    for i in range(n):
        row = {"date": str(df.index[i])[:10], "close": closes[i]}
        for p in [6, 12, 24]:
            if i < p:
                row[f"rsi{p}"] = None
                continue
            avg_gain = sum(gains[i - p + 1:i + 1]) / p
            avg_loss = sum(losses[i - p + 1:i + 1]) / p
            row[f"rsi{p}"] = 100.0 if avg_loss == 0 else round(100 - 100 / (1 + avg_gain / avg_loss), 2)
        rsi_rows.append(row)

    # KDJ
    k_val, d_val = 50.0, 50.0
    kdj_rows = []
    for i in range(n):
        if i < 8:
            kdj_rows.append({"date": str(df.index[i])[:10], "close": closes[i], "k": None, "d": None, "j": None})
            continue
        window_high = max(highs[i - 8:i + 1])
        window_low = min(lows[i - 8:i + 1])
        rsv = (closes[i] - window_low) / (window_high - window_low) * 100 if window_high != window_low else 50.0
        k_val = (1 / 3) * rsv + (2 / 3) * k_val
        d_val = (1 / 3) * k_val + (2 / 3) * d_val
        kdj_rows.append({
            "date": str(df.index[i])[:10], "close": closes[i],
            "k": round(k_val, 2), "d": round(d_val, 2),
            "j": round(3 * k_val - 2 * d_val, 2),
        })

    # Bollinger
    boll_rows = []
    for i in range(n):
        if i < 19:
            boll_rows.append({"date": str(df.index[i])[:10], "close": closes[i], "upper": None, "middle": None, "lower": None, "bandwidth": None})
            continue
        window = closes[i - 19:i + 1]
        ma = sum(window) / 20
        std = (sum((x - ma) ** 2 for x in window) / 20) ** 0.5
        upper = ma + 2 * std
        lower = ma - 2 * std
        boll_rows.append({
            "date": str(df.index[i])[:10], "close": closes[i],
            "upper": round(upper, 2), "middle": round(ma, 2), "lower": round(lower, 2),
            "bandwidth": round((upper - lower) / ma * 100, 2) if ma else None,
        })

    return {"ma": ma_rows, "macd": macd_rows, "rsi": rsi_rows, "kdj": kdj_rows, "boll": boll_rows}


# ---------------------------------------------------------------------------
# Supported indicator list
# ---------------------------------------------------------------------------

_SUPPORTED_INDICATORS = [
    "close_50_sma", "close_200_sma", "close_10_ema",
    "macd", "macds", "macdh",
    "rsi", "boll", "boll_ub", "boll_lb",
    "atr", "vwma", "mfi",
]

_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 SMA: Medium-term trend indicator.",
    "close_200_sma": "200 SMA: Long-term trend benchmark.",
    "close_10_ema": "10 EMA: Responsive short-term average.",
    "macd": "MACD: Momentum via EMA differences.",
    "macds": "MACD Signal: EMA smoothing of MACD line.",
    "macdh": "MACD Histogram: Gap between MACD and signal.",
    "rsi": "RSI: Momentum overbought/oversold indicator (70/30 thresholds).",
    "boll": "Bollinger Middle: 20 SMA basis for Bollinger Bands.",
    "boll_ub": "Bollinger Upper Band: 2 std devs above middle.",
    "boll_lb": "Bollinger Lower Band: 2 std devs below middle.",
    "atr": "ATR: Average True Range volatility measure.",
    "vwma": "VWMA: Volume-weighted moving average.",
    "mfi": "MFI: Money Flow Index (volume + price momentum).",
}


# ---------------------------------------------------------------------------
# Vendor Methods
# ---------------------------------------------------------------------------

def get_stock_data(
    symbol: Annotated[str, "ticker symbol (e.g. 02727.HK, AAPL)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Get OHLCV stock price data for HK or US stocks."""
    yahoo_code, tencent_code, market = _normalize_symbol(symbol)
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    if market == "hk":
        df = _yahoo_kline(f"{yahoo_code}.HK", "2y")
        data_source = "Yahoo Finance"
    else:
        df = _sina_us_kline(yahoo_code, 500)
        data_source = "Sina Finance"

    if df.empty:
        return f"No data found for '{symbol}' between {start_date} and {end_date}"

    df = df[(df.index >= start_dt) & (df.index <= end_dt)]
    if df.empty:
        return f"No data found for '{symbol}' between {start_date} and {end_date}"

    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    df = df.reset_index()
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    csv_out = df[["Date", "Open", "High", "Low", "Close", "Volume"]].to_csv(index=False)

    header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data source: {data_source}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_out


def get_indicators(
    symbol: Annotated[str, "ticker symbol (e.g. 02727.HK, AAPL)"],
    indicator: Annotated[str, "technical indicator name"],
    curr_date: Annotated[str, "Current date YYYY-mm-dd"],
    look_back_days: Annotated[int, "Days to look back"],
) -> str:
    """Get technical indicators for HK/US stocks."""
    yahoo_code, tencent_code, market = _normalize_symbol(symbol)

    if indicator not in _SUPPORTED_INDICATORS:
        return f"Indicator {indicator} not supported. Choose from: {_SUPPORTED_INDICATORS}"

    if market == "hk":
        df = _yahoo_kline(f"{yahoo_code}.HK", "1y")
    else:
        df = _yahoo_us_kline(yahoo_code, "1y")

    if df.empty:
        return f"No K-line data to calculate indicators for {symbol}"

    ind = _calc_indicators(df, yahoo_code)

    # Map indicator name to result key
    if indicator in ("close_50_sma", "close_200_sma", "close_10_ema"):
        rows = ind["ma"]
    elif indicator in ("macd", "macds", "macdh"):
        rows = ind["macd"]
    elif indicator.startswith("rsi"):
        rows = ind["rsi"]
    elif indicator in ("boll", "boll_ub", "boll_lb"):
        rows = ind["boll"]
    else:
        rows = ind["ma"]

    # Filter by look_back_days
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_dt - relativedelta(days=look_back_days)
    cutoff = curr_dt

    lines = []
    dt = before
    while dt <= cutoff:
        ds = dt.strftime("%Y-%m-%d")
        match = next((r for r in rows if r["date"] == ds), None)
        if match:
            if indicator in ("close_50_sma",):
                val = match.get("ma50", "N/A")
            elif indicator in ("close_200_sma",):
                val = match.get("ma200", "N/A")
            elif indicator in ("close_10_ema",):
                val = match.get("ma10", "N/A")
            elif indicator == "macd":
                val = f"DIF={match.get('dif')} DEA={match.get('dea')} HIST={match.get('macd_hist')}"
            elif indicator == "macds":
                val = match.get("dea", "N/A")
            elif indicator == "macdh":
                val = match.get("macd_hist", "N/A")
            elif indicator.startswith("rsi"):
                val = match.get(indicator, "N/A")
            elif indicator == "boll":
                val = f"MID={match.get('middle')} UB={match.get('upper')} LB={match.get('lower')}"
            elif indicator == "boll_ub":
                val = match.get("upper", "N/A")
            elif indicator == "boll_lb":
                val = match.get("lower", "N/A")
            else:
                val = "N/A"
        else:
            val = "N/A: Not a trading day"
        lines.append(f"{ds}: {val}")
        dt += relativedelta(days=1)

    return (
        f"## {indicator} values for {symbol} "
        f"from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + _INDICATOR_DESCRIPTIONS.get(indicator, "")
    )


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date (unused)"] = None,
) -> str:
    """Get real-time quote + key metrics for HK/US stocks."""
    yahoo_code, tencent_code, market = _normalize_symbol(ticker)
    lines = []

    if market == "hk":
        q = _hk_quote(tencent_code)
        if q:
            lines.extend([
                f"Name: {q['name']}",
                f"Price: {q['price']}",
                f"Change: {q['change_pct']}%",
                f"PE: {q['pe']}",
                f"PB: {q['pb']}",
                f"Market Cap (HKD): {q['market_cap']}",
            ])
    else:
        q = _us_quote(yahoo_code)
        if q:
            lines.extend([
                f"Name: {q['name']}",
                f"Price: {q['price']}",
                f"Change: {q['change_pct']}%",
                f"PE: {q['pe']}",
                f"EPS: {q['eps']}",
                f"Market Cap (USD): {q['market_cap']}",
            ])

    if not lines:
        return f"No fundamentals data found for '{ticker}'"

    header = f"# Company Fundamentals for {ticker}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + "\n".join(lines)


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: annual or quarterly"] = "annual",
    curr_date: Annotated[str, "current date YYYY-MM-DD"] = None,
) -> str:
    """Get balance sheet via Eastmoney datacenter."""
    yahoo_code, tencent_code, market = _normalize_symbol(ticker)
    is_hk = market == "hk"
    report_map = {
        "balance":   {"us": "RPT_USF10_FN_BALANCE",   "hk": "RPT_HKF10_FN_BALANCE"},
        "income":    {"us": "RPT_USF10_FN_INCOME",     "hk": "RPT_HKF10_FN_INCOME"},
        "cashflow": {"us": "RPT_USSK_FN_CASHFLOW",    "hk": "RPT_HKSK_FN_CASHFLOW"},
    }
    report_name = report_map.get("balance", {}).get(market)
    if not report_name:
        return f"No balance sheet for market {market}"

    # Eastmoney secucode: HK uses yahoo_code.HK format (e.g. 0700.HK)
    secucode = f"{yahoo_code}.HK" if is_hk else yahoo_code
    rows = _em_datacenter(report_name, filter_str=f'(SECUCODE="{secucode}")', page_size=200)

    if not rows:
        return f"No balance sheet data found for '{ticker}'"

    df = pd.DataFrame(rows)
    csv_out = df.to_csv(index=False)
    header = f"# Balance Sheet for {ticker} ({freq})\n"
    header += f"# Source: Eastmoney datacenter\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_out


def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: annual or quarterly"] = "annual",
    curr_date: Annotated[str, "current date YYYY-MM-DD"] = None,
) -> str:
    """Get cash flow statement via Eastmoney datacenter."""
    yahoo_code, tencent_code, market = _normalize_symbol(ticker)
    is_hk = market == "hk"
    report_map = {
        "balance":   {"us": "RPT_USF10_FN_BALANCE",   "hk": "RPT_HKF10_FN_BALANCE"},
        "income":    {"us": "RPT_USF10_FN_INCOME",     "hk": "RPT_HKF10_FN_INCOME"},
        "cashflow": {"us": "RPT_USSK_FN_CASHFLOW",    "hk": "RPT_HKSK_FN_CASHFLOW"},
    }
    report_name = report_map.get("cashflow", {}).get(market)
    if not report_name:
        return f"No cash flow for market {market}"

    secucode = f"{yahoo_code}.HK" if is_hk else yahoo_code
    rows = _em_datacenter(report_name, filter_str=f'(SECUCODE="{secucode}")', page_size=200)

    if not rows:
        return f"No cash flow data found for '{ticker}'"

    df = pd.DataFrame(rows)
    csv_out = df.to_csv(index=False)
    header = f"# Cash Flow for {ticker} ({freq})\n"
    header += f"# Source: Eastmoney datacenter\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_out


def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: annual or quarterly"] = "annual",
    curr_date: Annotated[str, "current date YYYY-MM-DD"] = None,
) -> str:
    """Get income statement via Eastmoney datacenter."""
    yahoo_code, tencent_code, market = _normalize_symbol(ticker)
    is_hk = market == "hk"
    report_map = {
        "balance":   {"us": "RPT_USF10_FN_BALANCE",   "hk": "RPT_HKF10_FN_BALANCE"},
        "income":    {"us": "RPT_USF10_FN_INCOME",     "hk": "RPT_HKF10_FN_INCOME"},
        "cashflow": {"us": "RPT_USSK_FN_CASHFLOW",    "hk": "RPT_HKSK_FN_CASHFLOW"},
    }
    report_name = report_map.get("income", {}).get(market)
    if not report_name:
        return f"No income statement for market {market}"

    secucode = f"{yahoo_code}.HK" if is_hk else yahoo_code
    rows = _em_datacenter(report_name, filter_str=f'(SECUCODE="{secucode}")', page_size=200)

    if not rows:
        return f"No income statement data found for '{ticker}'"

    df = pd.DataFrame(rows)
    csv_out = df.to_csv(index=False)
    header = f"# Income Statement for {ticker} ({freq})\n"
    header += f"# Source: Eastmoney datacenter\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_out


def get_news(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "Start date yyyy-mm-dd"],
    end_date: Annotated[str, "End date yyyy-mm-dd"],
) -> str:
    """Get stock news via Yahoo Finance search."""
    yahoo_code, tencent_code, market = _normalize_symbol(ticker)
    symbol = yahoo_code if market == "us" else f"{yahoo_code}.HK"

    try:
        s = requests.Session()
        s.headers["User-Agent"] = _UA
        s.get("https://fc.yahoo.com", timeout=10)
        r = s.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": symbol, "quotesCount": 0, "newsCount": 20}, timeout=10,
        )
        r.raise_for_status()
        news_data = r.json().get("news", [])

        if not news_data:
            return f"No news found for '{ticker}'"

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        lines = [f"# News for {ticker} ({start_date} to {end_date})\n"]
        count = 0
        for n in news_data:
            pub_ts = n.get("providerPublishTime", 0)
            if not pub_ts:
                continue
            pub_dt = datetime.fromtimestamp(pub_ts)
            if pub_dt < start_dt or pub_dt > end_dt:
                continue
            lines.append(f"### {n.get('title', '')} ({n.get('publisher', '')})")
            lines.append(f"Link: {n.get('link', '')}\n")
            count += 1

        if count == 0:
            return f"No news found for '{ticker}' between {start_date} and {end_date}"

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching news for {ticker}: {e}"


def get_global_news(
    curr_date: Annotated[str, "Current date yyyy-mm-dd"],
    look_back_days: Annotated[int, "Days to look back"] = 7,
    limit: Annotated[int, "Max articles"] = 10,
) -> str:
    """Get global financial news via Yahoo Finance."""
    start_dt = datetime.strptime(curr_date, "%Y-%m-%d") - relativedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    try:
        s = requests.Session()
        s.headers["User-Agent"] = _UA
        s.get("https://fc.yahoo.com", timeout=10)
        r = s.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": "stock market finance", "quotesCount": 0, "newsCount": limit * 3}, timeout=10,
        )
        r.raise_for_status()
        news_data = r.json().get("news", [])

        if not news_data:
            return f"No global news found for {curr_date}"

        lines = [f"## Global Financial News, {start_date} to {curr_date}:\n"]
        count = 0
        for n in news_data:
            pub_ts = n.get("providerPublishTime", 0)
            if not pub_ts:
                continue
            pub_dt = datetime.fromtimestamp(pub_ts)
            if pub_dt < start_dt or pub_dt > datetime.strptime(curr_date, "%Y-%m-%d"):
                continue
            lines.append(f"### {n.get('title', '')} ({n.get('publisher', '')})")
            if n.get("link"):
                lines.append(f"Link: {n.get('link')}")
            count += 1
            if count >= limit:
                break

        if count == 0:
            return f"No global news found for {curr_date}"

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching global news: {e}"