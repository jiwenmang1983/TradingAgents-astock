# Global Stock Data Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add HK/US stock data support via new `global_stock.py` vendor in `dataflows/`. Agent tool interface unchanged.

**Architecture:** A new `global_stock` vendor is added to `interface.py`'s `VENDOR_LIST` and `VENDOR_METHODS`. Market detection is ticker-format-based (`.HK`→HK, `.O`/`.N`→US, etc.). `default_config.py` gets new vendor routing defaults.

**Tech Stack:** Python 3.10+, requests, pandas, numpy (for indicator calculations). Existing moottdx/yfinance patterns followed.

---

## File Map

| File | Role |
|------|------|
| `tradingagents/dataflows/global_stock.py` | **NEW** — all HK/US data methods |
| `tradingagents/dataflows/interface.py` | **MODIFY** — add global_stock to VENDOR_LIST + VENDOR_METHODS |
| `tradingagents/default_config.py` | **MODIFY** — add global_stock vendor defaults |
| `tests/tradingagents/dataflows/test_global_stock.py` | **NEW** — unit tests |

---

## Helper: _detect_market

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

### Task 1: Write _detect_market helper

- [ ] **Step 1: Write the test**

```python
# tests/tradingagents/dataflows/test_global_stock.py
import pytest
from tradingagents.dataflows.global_stock import _detect_market

def test_detect_hk():
    assert _detect_market("02727.HK") == "hk"
    assert _detect_market("00700.HK") == "hk"
    assert _detect_market("700") == "hk"
    assert _detect_market("00700") == "hk"

def test_detect_us():
    assert _detect_market("AAPL") == "us"
    assert _detect_market("AAPL.O") == "us"
    assert _detect_market("BABA.N") == "us"
    assert _detect_market("TSLA") == "us"

def test_detect_astock():
    assert _detect_market("600000") == "astock"
    assert _detect_market("000858") == "astock"
    assert _detect_market("688017") == "astock"
    assert _detect_market("600000.SS") == "astock"
    assert _detect_market("000001.SZ") == "astock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/tradingagents/dataflows/test_global_stock.py::test_detect_hk -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal _detect_market implementation**

```python
# tradingagents/dataflows/global_stock.py
from __future__ import annotations
from typing import Literal

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/tradingagents/dataflows/test_global_stock.py::test_detect_hk tests/tradingagents/dataflows/test_global_stock.py::test_detect_us tests/tradingagents/dataflows/test_global_stock.py::test_detect_astock -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/tradingagents/dataflows/test_global_stock.py tradingagents/dataflows/global_stock.py
git commit -m "feat(global_stock): add _detect_market ticker format detection"
```

---

## Helper: Normalize code

### Task 2: Write _normalize_symbol helper

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_normalize_hk():
    from tradingagents.dataflows.global_stock import _normalize_symbol
    assert _normalize_symbol("02727.HK") == ("2727", "hk")
    assert _normalize_symbol("700") == ("00700", "hk")
    assert _normalize_symbol("00700") == ("00700", "hk")

def test_normalize_us():
    from tradingagents.dataflows.global_stock import _normalize_symbol
    assert _normalize_symbol("AAPL") == ("AAPL", "us")
    assert _normalize_symbol("AAPL.O") == ("AAPL.O", "us")
    assert _normalize_symbol("BABA.N") == ("BABA.N", "us")

def test_normalize_astock():
    from tradingagents.dataflows.global_stock import _normalize_symbol
    assert _normalize_symbol("600000") == ("600000", "astock")
    assert _normalize_symbol("000001.SZ") == ("000001", "astock")
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write _normalize_symbol**

```python
def _normalize_symbol(symbol: str) -> tuple[str, str]:
    """Normalize symbol to (normalized_code, market)."""
    s = symbol.strip()
    market = _detect_market(s)

    if market == "hk":
        code = s.split(".")[0].strip()
        code = code.zfill(5)
        return code, "hk"

    if market == "us":
        return s.upper(), "us"

    # astock — strip .SS/.SZ
    for suffix in (".SS", ".SZ", ".BJ"):
        if s.upper().endswith(suffix):
            s = s[: -len(suffix)]
            break
    for prefix in ("SH", "SZ", "BJ"):
        if s.upper().startswith(prefix):
            s = s[len(prefix):]
            break
    return s.strip(), "astock"
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

## Data Source Helpers

### Task 3: HK quote helper (_hk_quote)

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_hk_quote():
    from tradingagents.dataflows.global_stock import _hk_quote
    result = _hk_quote("00700")
    assert result["name"] == "腾讯控股"
    assert "price" in result
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write _hk_quote**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 4: US quote helper (_us_quote)

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_us_quote():
    from tradingagents.dataflows.global_stock import _us_quote
    result = _us_quote("AAPL")
    assert result["name"] == "Apple Inc."
    assert "price" in result
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write _us_quote**

```python
def _us_quote(ticker: str) -> dict:
    """Get US real-time quote from Sina hq.sinajs.cn."""
    url = f"https://hq.sinajs.cn/list=gb_{ticker.lower()}"
    req = urllib.request.Request(url)
    req.add_header("Referer", "https://finance.sina.com.cn/")
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    r.encoding = "gbk"
    m = re.search(r'"(.+)"', r.text)
    if not m:
        return {}
    fields = m.group(1).split(",")
    if len(fields) < 30:
        return {}
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
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 5: Yahoo Finance K-line helper (_yahoo_kline)

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_yahoo_kline_hk():
    from tradingagents.dataflows.global_stock import _yahoo_kline
    df = _yahoo_kline("02727.HK", "1mo")
    assert not df.empty
    assert set(df.columns) == {"Date", "Open", "High", "Low", "Close", "Volume"}

def test_yahoo_kline_us():
    from tradingagents.dataflows.global_stock import _yahoo_kline
    df = _yahoo_kline("AAPL", "1mo")
    assert not df.empty
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write _yahoo_kline**

```python
def _yahoo_kline(symbol: str, range_: str = "6mo") -> pd.DataFrame:
    """Fetch OHLCV from Yahoo Finance chart API."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": range_}
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
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
    return df.dropna()
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 6: Sina US K-line helper (_sina_us_kline)

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_sina_us_kline():
    from tradingagents.dataflows.global_stock import _sina_us_kline
    df = _sina_us_kline("AAPL", 120)
    assert not df.empty
    assert set(df.columns) == {"Date", "Open", "High", "Low", "Close", "Volume"}
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write _sina_us_kline**

```python
def _sina_us_kline(ticker: str, num: int = 120) -> pd.DataFrame:
    """Fetch US daily K-line from Sina Finance (back to 1984)."""
    url = (
        "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/"
        "var US_MinKService.getDailyK"
    )
    params = {"symbol": ticker.upper(), "num": num}
    headers = {"Referer": "https://finance.sina.com.cn/"}
    r = requests.get(url, params=params, headers=headers, timeout=15)
    m = re.search(r"\((.+)\)", r.text, re.DOTALL)
    if not m:
        return pd.DataFrame()
    items = json.loads(m.group(1))
    rows = [{
        "Date": it["d"],
        "Open": float(it["o"]),
        "High": float(it["h"]),
        "Low": float(it["l"]),
        "Close": float(it["c"]),
        "Volume": int(it["v"]),
    } for it in items]
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 7: Eastmoney datacenter helper (_em_datacenter)

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_em_datacenter_hk_balance():
    from tradingagents.dataflows.global_stock import _em_datacenter
    rows = _em_datacenter("RPT_HKF10_FN_BALANCE", filter_str='(SECUCODE="00700.HK")')
    assert len(rows) > 0

def test_em_datacenter_us_balance():
    from tradingagents.dataflows.global_stock import _em_datacenter
    rows = _em_datacenter("RPT_USF10_FN_BALANCE", filter_str='(SECUCODE="AAPL.O")')
    assert len(rows) > 0
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write _em_datacenter**

```python
_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

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
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 8: Technical indicator calculator (_calc_indicators)

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_calc_indicators():
    from tradingagents.dataflows.global_stock import _calc_indicators
    # Build test df
    import pandas as pd
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame({
        "Close": [100 + i for i in range(50)],
        "High": [105 + i for i in range(50)],
        "Low": [95 + i for i in range(50)],
    }, index=dates)
    df.index.name = "Date"
    result = _calc_indicators(df, "AAPL")
    assert "ma" in result
    assert "rsi" in result
    assert "macd" in result
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write _calc_indicators**

Implement MA/EMA/MACD/RSI/KDJ/Bollinger from vibe-trading's `us_stock_technicals`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

## Vendor Methods

### Task 9: get_stock_data

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_get_stock_data_hk():
    from tradingagents.dataflows.global_stock import get_stock_data
    result = get_stock_data("02727.HK", "2024-01-01", "2024-12-31")
    assert "# Stock data" in result
    assert "02727" in result
    assert "2024" in result

def test_get_stock_data_us():
    from tradingagents.dataflows.global_stock import get_stock_data
    result = get_stock_data("AAPL", "2024-01-01", "2024-12-31")
    assert "# Stock data" in result
    assert "AAPL" in result
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write get_stock_data**

```python
def get_stock_data(
    symbol: Annotated[str, "ticker symbol (e.g. 02727.HK, AAPL)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Get OHLCV stock price data for HK or US stocks."""
    norm, market = _normalize_symbol(symbol)
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    if market == "hk":
        yahoo_sym = f"{int(norm)}.HK"
        df = _yahoo_kline(yahoo_sym, "2y")
        data_source = "Yahoo Finance"
    else:
        df = _sina_us_kline(norm, 800)
        data_source = "Sina Finance"

    if df.empty:
        return f"No data found for '{symbol}' between {start_date} and {end_date}"

    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]
    if df.empty:
        return f"No data found for '{symbol}' between {start_date} and {end_date}"

    for col in ["Open", "High", "Low", "Close"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    csv_out = df[["Date", "Open", "High", "Low", "Close", "Volume"]].to_csv(index=False)

    header = f"# Stock data for {symbol} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data source: {data_source}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_out
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 10: get_indicators

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_get_indicators():
    from tradingagents.dataflows.global_stock import get_indicators
    result = get_indicators("AAPL", "rsi", "2024-06-01", 30)
    assert "RSI" in result
    assert "2024" in result
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write get_indicators**

```python
_SUPPORTED_INDICATORS = [
    "close_50_sma", "close_200_sma", "close_10_ema",
    "macd", "macds", "macdh",
    "rsi", "boll", "boll_ub", "boll_lb",
    "atr", "vwma", "mfi",
]

def get_indicators(
    symbol: Annotated[str, "ticker symbol (e.g. 02727.HK, AAPL)"],
    indicator: Annotated[str, "technical indicator name"],
    curr_date: Annotated[str, "Current date YYYY-mm-dd"],
    look_back_days: Annotated[int, "Days to look back"],
) -> str:
    """Get technical indicators for HK/US stocks."""
    norm, market = _normalize_symbol(symbol)

    if indicator not in _SUPPORTED_INDICATORS:
        return f"Indicator {indicator} not supported. Choose from: {_SUPPORTED_INDICATORS}"

    if market == "hk":
        df = _yahoo_kline(f"{int(norm)}.HK", "1y")
    else:
        df = _sina_us_kline(norm, 250)

    if df.empty:
        return f"No K-line data to calculate indicators for {symbol}"

    ind = _calc_indicators(df, norm)

    # Map our internal indicators to the right keys
    if indicator in ("close_50_sma", "close_200_sma", "close_10_ema"):
        p = int(indicator.split("_")[1][:2])
        key = f"ma{p if p < 20 else (60 if p == 200 else (10 if p == 10 else p))}"
        rows = ind["ma"]
    elif indicator == "macd":
        rows = ind["macd"]
    elif indicator == "macds":
        rows = ind["macd"]
    elif indicator == "macdh":
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
        val = match.get(indicator.split("_")[-1], "N/A") if match else "N/A"
        lines.append(f"{ds}: {val}")
        dt += relativedelta(days=1)

    return (
        f"## {indicator} values for {symbol} "
        f"from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(lines)
    )
```

Note: Simplify indicator mapping. Use `_INDICATOR_DESCRIPTIONS` dict matching `a_stock.py`.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 11: get_fundamentals

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_get_fundamentals_hk():
    from tradingagents.dataflows.global_stock import get_fundamentals
    result = get_fundamentals("00700.HK", "2024-06-01")
    assert "腾讯控股" in result or "00700" in result

def test_get_fundamentals_us():
    from tradingagents.dataflows.global_stock import get_fundamentals
    result = get_fundamentals("AAPL", "2024-06-01")
    assert "Apple" in result or "AAPL" in result
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write get_fundamentals**

```python
def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date (unused)"] = None,
) -> str:
    """Get real-time quote + key metrics for HK/US stocks."""
    norm, market = _normalize_symbol(ticker)
    lines = []

    if market == "hk":
        q = _hk_quote(norm)
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
        q = _us_quote(norm)
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
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 12: Financial statements (balance/cashflow/income)

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_get_balance_sheet_hk():
    from tradingagents.dataflows.global_stock import get_balance_sheet
    result = get_balance_sheet("00700.HK", "annual", "2024-06-01")
    assert "balance" in result.lower() or "00700" in result

def test_get_income_statement_us():
    from tradingagents.dataflows.global_stock import get_income_statement
    result = get_income_statement("AAPL.O", "annual", "2024-06-01")
    assert "income" in result.lower() or "AAPL" in result
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write financial statement methods**

```python
def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "frequency: annual or quarterly"] = "annual",
    curr_date: Annotated[str, "current date YYYY-MM-DD"] = None,
) -> str:
    norm, market = _normalize_symbol(ticker)
    is_hk = market == "hk"
    report_map = {
        "balance":   {"us": "RPT_USF10_FN_BALANCE",   "hk": "RPT_HKF10_FN_BALANCE"},
        "income":    {"us": "RPT_USF10_FN_INCOME",     "hk": "RPT_HKF10_FN_INCOME"},
        "cashflow": {"us": "RPT_USSK_FN_CASHFLOW",    "hk": "RPT_HKSK_FN_CASHFLOW"},
    }
    report_name = report_map.get("balance", {}).get(market)
    if not report_name:
        return f"No balance sheet for market {market}"

    secucode = norm if is_hk else norm
    rows = _em_datacenter(report_name, filter_str=f'(SECUCODE="{secucode}")', page_size=200)

    if not rows:
        return f"No balance sheet data found for '{ticker}'"

    df = pd.DataFrame(rows)
    csv_out = df.to_csv(index=False)
    header = f"# Balance Sheet for {ticker} ({freq})\n"
    header += f"# Source: Eastmoney datacenter\n"
    header += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_out

# get_cashflow and get_income_statement follow the same pattern with different report_map keys
```

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

### Task 13: get_news and get_global_news

**Files:**
- Modify: `tradingagents/dataflows/global_stock.py`

- [ ] **Step 1: Write the test**

```python
def test_get_news():
    from tradingagents.dataflows.global_stock import get_news
    result = get_news("AAPL", "2024-01-01", "2024-06-01")
    assert "AAPL" in result or "Apple" in result or "news" in result.lower()
```

- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Write get_news**

Use Yahoo Finance search (from vibe-trading `stock_news`):
```python
def get_news(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "Start date yyyy-mm-dd"],
    end_date: Annotated[str, "End date yyyy-mm-dd"],
) -> str:
    norm, market = _normalize_symbol(ticker)
    symbol = norm if market == "us" else f"{norm}.HK"

    try:
        s = requests.Session()
        s.headers["User-Agent"] = "Mozilla/5.0"
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
```

get_global_news for HK/US: use same Yahoo Finance search approach filtered to market news.

- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

---

## Interface Wiring

### Task 14: Wire into interface.py

**Files:**
- Modify: `tradingagents/dataflows/interface.py`

- [ ] **Step 1: Add imports**

```python
from .global_stock import (
    get_stock_data as get_global_stock_stock_data,
    get_indicators as get_global_stock_indicators,
    get_fundamentals as get_global_stock_fundamentals,
    get_balance_sheet as get_global_stock_balance_sheet,
    get_cashflow as get_global_stock_cashflow,
    get_income_statement as get_global_stock_income_statement,
    get_news as get_global_stock_news,
    get_global_news as get_global_stock_global_news,
)
```

- [ ] **Step 2: Add global_stock to VENDOR_LIST**

```python
VENDOR_LIST = [
    "a_stock",
    "yfinance",
    "alpha_vantage",
    "global_stock",  # NEW
]
```

- [ ] **Step 3: Add to VENDOR_METHODS**

```python
VENDOR_METHODS = {
    # ... existing entries ...
    "get_stock_data": {
        "a_stock": get_astock_stock_data,
        "global_stock": get_global_stock_stock_data,
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    "get_indicators": {
        "a_stock": get_astock_indicators,
        "global_stock": get_global_stock_indicators,
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    "get_fundamentals": {
        "a_stock": get_astock_fundamentals,
        "global_stock": get_global_stock_fundamentals,
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "a_stock": get_astock_balance_sheet,
        "global_stock": get_global_stock_balance_sheet,
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "a_stock": get_astock_cashflow,
        "global_stock": get_global_stock_cashflow,
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "a_stock": get_astock_income_statement,
        "global_stock": get_global_stock_income_statement,
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    "get_news": {
        "a_stock": get_astock_news,
        "global_stock": get_global_stock_news,
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "a_stock": get_astock_global_news,
        "global_stock": get_global_stock_global_news,
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
}
```

- [ ] **Step 4: Verify no import errors**

Run: `python -c "from tradingagents.dataflows.interface import route_to_vendor; print('OK')"`

- [ ] **Step 5: Commit**

---

### Task 15: Wire into default_config.py

**Files:**
- Modify: `tradingagents/default_config.py`

- [ ] **Step 1: Update data_vendors to include global_stock**

```python
"data_vendors": {
    "core_stock_apis": "a_stock,global_stock",  # global_stock added
    "technical_indicators": "a_stock,global_stock",
    "fundamental_data": "a_stock,global_stock",
    "news_data": "a_stock,global_stock",
    "signal_data": "a_stock",
},
```

- [ ] **Step 2: Commit**

```bash
git add tradingagents/default_config.py
git commit -m "feat: add global_stock to vendor routing defaults"
```

---

## Spec Coverage Check

- [x] Market detection: Task 1-2
- [x] HK data sources: Tasks 3, 5, 7
- [x] US data sources: Tasks 4, 6, 7
- [x] get_stock_data: Task 9
- [x] get_indicators: Task 8, 10
- [x] get_fundamentals: Task 4, 11
- [x] Financial statements: Task 12
- [x] get_news: Task 13
- [x] get_global_news: Task 13
- [x] interface.py wiring: Task 14
- [x] default_config.py wiring: Task 15

**Plan complete.** Saved to `docs/superpowers/plans/2026-05-26-global-stock-data-implementation.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?