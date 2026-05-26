# Global Stock Data Integration — Design

## Status
- **Author**: Claude
- **Created**: 2026-05-26
- **Approved by**: user

## Goal
Add HK/US stock data support to TradingAgents via a new `global_stock.py` dataflows module. Agent tool interface remains unchanged.

---

## 1. Architecture Overview

```
interface.py (unchanged)
  └── VENDOR_METHODS[method]["global_stock"] ──→ global_stock.py
                                               (HK/US data sources)

dataflows/
  ├── a_stock.py      # A股 (mootdx)
  ├── y_finance.py    # Global fallback (yfinance)
  ├── global_stock.py # NEW: HK/US (this design)
  └── interface.py    # unchanged
```

A new vendor `"global_stock"` is added to `VENDOR_LIST` and mapped per-method in `VENDOR_METHODS`.

**Vendors flow**:
- If `a_stock` ticker → `a_stock.py` (existing)
- If HK/US ticker → `global_stock.py` (new)
- Fallback chain remains unchanged

---

## 2. Ticker Market Detection

Rules (applied in order):

| Pattern | Market | Examples |
|---------|--------|----------|
| Ends with `.HK` | HK | `02727.HK`, `00700.HK` |
| Ends with `.O` | US NYSE | `AAPL.O` |
| Ends with `.N` | US NASDAQ | `BABA.N` |
| Ends with `.SS` | A股 Shanghai | `600000.SS` |
| Ends with `.SZ` | A股 Shenzhen | `000001.SZ` |
| 6-digit number | A股 | `688017`, `000858` |
| 4-5 digit number | HK | `700`, `2727`, `00700` |
| Pure uppercase letters | US | `AAPL`, `TSLA`, `BABA` |

Implementation: `_detect_market(symbol: str) -> Literal["hk", "us", "astock"]`

---

## 3. Data Sources

### 3a. HK Data Sources

| Data Type | Source | API |
|-----------|--------|-----|
| Real-time quote | Tencent qt.gtimg.cn | `r_hk{5-digit-code}` |
| K-line daily | Yahoo Finance chart | `https://query2.finance.yahoo.com/v8/finance/chart/{code}.HK` |
| K-line intraday | Yahoo Finance chart | interval=5m/15m/1h |
| Balance sheet | Eastmoney datacenter | `RPT_HKF10_FN_BALANCE` |
| Income statement | Eastmoney datacenter | `RPT_HKF10_FN_INCOME` |
| Cash flow | Eastmoney datacenter | `RPT_HKSK_FN_CASHFLOW` |
| Key indicators | Eastmoney datacenter | `RPT_HKF10_FN_GMAININDICATOR` |
| Fund flow daily | Eastmoney push2his | `secid=116.{code}` |
| News | Yahoo Finance search | `/v1/finance/search` |

### 3b. US Data Sources

| Data Type | Source | API |
|-----------|--------|-----|
| Real-time quote | Sina hq.sinajs.cn | `gb_{ticker.lower()}` |
| K-line daily | Sina stock.finance.sina.com.cn | `/US_MinKService.getDailyK` |
| Balance sheet | Eastmoney datacenter | `RPT_USF10_FN_BALANCE` |
| Income statement | Eastmoney datacenter | `RPT_USF10_FN_INCOME` |
| Cash flow | Eastmoney datacenter | `RPT_USSK_FN_CASHFLOW` |
| Key indicators | Eastmoney datacenter | `RPT_USF10_FN_GMAININDICATOR` |
| Fund flow daily | Eastmoney push2his | `secid=105.{code}` (NASDAQ) or `106.{code}` (NYSE) |
| News | Yahoo Finance search | `/v1/finance/search` |

---

## 4. Methods Implemented

All signatures match `a_stock.py` interface for transparent routing.

| Method | HK | US | Notes |
|--------|----|----|-------|
| `get_stock_data` | ✓ | ✓ | OHLCV, date range filter |
| `get_indicators` | ✓ | ✓ | MA/MACD/RSI/KDJ/Boll |
| `get_fundamentals` | ✓ | ✓ | Real-time quote + key stats |
| `get_balance_sheet` | ✓ | ✓ | Annual/quarterly |
| `get_cashflow` | ✓ | ✓ | Annual/quarterly |
| `get_income_statement` | ✓ | ✓ | Annual/quarterly |
| `get_news` | ✓ | ✓ | Date range filter |
| `get_global_news` | ✓ | ✓ | Returns HK/US news (cls/eastmoney not applicable) |
| `get_insider_transactions` | — | — | N/A for HK/US |

Technical indicators computed locally from K-line data (same logic as vibe-trading `us_stock_technicals`).

---

## 5. Technical Indicator Calculation

Computed client-side from K-line data (no external API needed):

- **MA**: Simple moving average (5/10/20/60 periods)
- **EMA**: Exponential moving average
- **MACD**: DIF/DEA/macd_hist (12/26/9 periods)
- **RSI**: RSI (6/12/24 periods)
- **KDJ**: K/D/J (9 periods lookback)
- **Bollinger Bands**: 20-period middle band ± 2 std dev

---

## 6. Error Handling

- Each API call wrapped in try/except
- On API failure: return descriptive error string (no exception propagation)
- On empty data: return `"No data found for ..."` message
- Rate limiting: same retry pattern as existing code

---

## 7. Configuration

Vendors per method in `interface.py`:

```python
"get_stock_data": {
    "a_stock": get_astock_stock_data,
    "global_stock": get_global_stock_data,  # NEW
    "yfinance": get_YFin_data_online,
},
```

Tool-level config in `default_config.py` takes precedence.

---

## 8. Files to Change

1. **NEW**: `tradingagents/dataflows/global_stock.py` — all HK/US data methods
2. **MODIFY**: `tradingagents/dataflows/interface.py` — add `"global_stock"` to vendors and methods
3. **MODIFY**: `tradingagents/default_config.py` — add vendor routing defaults

---

## 9. Scope

**In scope**:
- HK and US stock data (OHLCV, indicators, fundamentals, financials, news, fund flow)
- Automatic market detection from ticker format
- Interface-compatible with existing Agent tools

**Out of scope** (future):
- Options data
- SEC filings
- Stock search / market list
- Broker-specific data