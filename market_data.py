from concurrent.futures import ThreadPoolExecutor
import yfinance as yf
import requests
import os
from dotenv import load_dotenv

load_dotenv()
import threading
import time

_enriched_data_cache = {"data": {}, "timestamp": 0}
_enriched_data_lock = threading.Lock()
ENRICHED_DATA_TTL_SECONDS = 7200  # 2 hours

# ── Curated instrument lists by risk ─────────────────────
STOCKS_LONG_TERM = {
    "low":    ["VTI", "VOO", "SCHD", "VYM", "BRK-B", "V", "MA", "LIN", "ABT"],
    "medium": ["VOO", "VTI", "MSFT", "AAPL", "JNJ", "ACN", "TMO", "TXN"],
    "high":   ["MSFT", "AAPL", "NVDA", "GOOGL", "AMZN", "CRM", "ADBE", "ISRG"]
}

STOCKS_SHORT_TERM = {
    "low":    ["VIG", "NOBL", "SDY"],
    "medium": ["QQQ", "SPY", "META", "TSLA"],
    "high":   ["NVDA", "META", "TSLA", "AMD", "ARKK", "PANW", "SNPS", "LRCX", "NOW", "NFLX", "INTU"]
}

BONDS = {
    "low":    ["BND", "AGG", "MUB", "TIP"],
    "medium": ["BND", "AGG", "TLT", "LQD"],
    "high":   ["HYG", "JNK", "TLT", "EMB"]
}

MUTUAL_FUNDS = {
    "low":    ["VFIAX", "VBTLX", "VWELX", "SWPPX"],
    "medium": ["VFIAX", "FXAIX", "VWELX", "SWPPX", "PRGFX"],
    "high":   ["FXAIX", "FOCPX", "VIMAX", "AGTHX", "FCNTX", "FBGRX"]
}


# ── Fetch single ticker ───────────────────────────────────
def fetch_single_ticker(ticker):
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info

        price       = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice", 0)
        name        = info.get("longName") or info.get("shortName", ticker)
        pe          = info.get("trailingPE", None)
        div_yield   = info.get("dividendYield", None)
        week52_high = info.get("fiftyTwoWeekHigh", None)
        week52_low  = info.get("fiftyTwoWeekLow", None)
        expense     = info.get("annualReportExpenseRatio", None)

        return {
            "ticker":         ticker,
            "name":           name,
            "price":          round(price, 2) if price else "N/A",
            "pe_ratio":       round(pe, 1) if pe else "N/A",
            "dividend_yield": f"{round(div_yield * 100, 2)}%" if div_yield and div_yield < 1 else f"{round(div_yield, 2)}%" if div_yield else "N/A",
            "52w_high":       round(week52_high, 2) if week52_high else "N/A",
            "52w_low":        round(week52_low, 2) if week52_low else "N/A",
            "expense_ratio":  f"{round(expense * 100, 2)}%" if expense else "N/A",
        }

    except Exception:
        return {
            "ticker":         ticker,
            "name":           ticker,
            "price":          "N/A",
            "pe_ratio":       "N/A",
            "dividend_yield": "N/A",
            "52w_high":       "N/A",
            "52w_low":        "N/A",
            "expense_ratio":  "N/A",
        }


# ── Fetch stock data ──────────────────────────────────────
def get_stock_data(risk, category="long"):
    from concurrent.futures import ThreadPoolExecutor
    risk = risk.lower()

    if category == "long":
        tickers = STOCKS_LONG_TERM.get(risk, STOCKS_LONG_TERM["medium"])
    elif category == "short":
        tickers = STOCKS_SHORT_TERM.get(risk, STOCKS_SHORT_TERM["medium"])
    elif category == "bonds":
        tickers = BONDS.get(risk, BONDS["medium"])
    else:
        tickers = MUTUAL_FUNDS.get(risk, MUTUAL_FUNDS["medium"])

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(fetch_single_ticker, tickers))

    return results

# ── Fetch Treasury & CD rates from FRED ──────────────────
def get_rates():
    fred_key = os.getenv("FRED_API_KEY")
    rates    = {}

    series = {
        "3_month_treasury": "TB3MS",
        "6_month_treasury": "TB6MS",
        "1_year_treasury":  "GS1",
        "5_year_treasury":  "GS5",
        "10_year_treasury": "GS10",
        "30_year_treasury": "GS30",
    }

    for label, series_id in series.items():
        try:
            url    = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id":  series_id,
                "api_key":    fred_key,
                "sort_order": "desc",
                "limit":      1,
                "file_type":  "json"
            }
            resp  = requests.get(url, params=params, timeout=5)
            data  = resp.json()
            value = data["observations"][0]["value"]
            rates[label] = float(value)
        except Exception:
            rates[label] = None

    if rates.get("6_month_treasury"):
        rates["cd_3_month"] = round(rates["6_month_treasury"] + 0.10, 2)
        rates["cd_6_month"] = round(rates["6_month_treasury"] + 0.15, 2)
        rates["cd_1_year"]  = round(rates.get("1_year_treasury", 5.0) + 0.10, 2)

    return rates


# ── Get all market data for a client profile ─────────────
def get_all_market_data(risk):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_lt     = executor.submit(get_stock_data, risk, "long")
        future_st     = executor.submit(get_stock_data, risk, "short")
        future_bonds  = executor.submit(get_stock_data, risk, "bonds")
        future_mutual = executor.submit(get_stock_data, risk, "mutual")
        future_rates  = executor.submit(get_rates)

        return {
            "stocks_lt":    future_lt.result(),
            "stocks_st":    future_st.result(),
            "bonds":        future_bonds.result(),
            "mutual_funds": future_mutual.result(),
            "rates":        future_rates.result()
        }

def fetch_instrument_prices(instruments):
    """
    Fetches current prices for all instruments in a recommendation.
    Called when saving a recommendation to store original prices.
    Returns dict: {ticker: price}
    """
    prices = {}
    all_tickers = []

    for cat, items in instruments.items():
        for inst in items:
            ticker = inst.get("ticker", "")
            if ticker and not ticker.startswith("CD-") and ticker != "TBILL":
                all_tickers.append(ticker)

    if not all_tickers:
        return prices

    def fetch_one(ticker):
        try:
            info  = yf.Ticker(ticker).info
            price = info.get("regularMarketPrice") or \
                    info.get("currentPrice") or \
                    info.get("navPrice", 0)
            return ticker, float(price) if price else 0
        except Exception:
            return ticker, 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_one, all_tickers)
        for ticker, price in results:
            prices[ticker] = price

    return prices

def get_enriched_instrument_data(tickers):
    """
    Fetches current fundamental data (price, P/E, dividend yield) for
    a list of tickers, formatted for inclusion in the AI prompt so
    recommendations are grounded in real numbers instead of the
    model's training-time memory.
    Returns dict: {ticker: {"price": ..., "pe_ratio": ..., "dividend_yield": ...}}
    """
    def fetch_one(ticker):
        try:
            if ticker.startswith("CD-") or ticker == "TBILL":
                return ticker, None
            info = yf.Ticker(ticker).info
            price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
            pe = info.get("trailingPE")
            div_yield = info.get("dividendYield")
            return ticker, {
                "price": round(price, 2) if price else None,
                "pe_ratio": round(pe, 1) if pe else None,
                "dividend_yield": round(div_yield * 100, 2) if div_yield and div_yield < 1 else (round(div_yield, 2) if div_yield else None)
            }
        except Exception:
            return ticker, None

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = dict(executor.map(fetch_one, tickers))

    return {k: v for k, v in results.items() if v is not None}

def get_cached_enriched_data(tickers):
    """
    Returns enriched instrument data from cache if fresh, otherwise
    fetches once and caches for all tickers together, shared across
    every recommendation generated within the TTL window. The lock is
    held across the fetch itself so concurrent callers (e.g. all 4
    options generating in parallel) don't each redundantly re-fetch
    on a cold cache — only the first one fetches, others wait and
    reuse its result.
    """
    now = time.time()

    with _enriched_data_lock:
        cached = _enriched_data_cache
        if cached["data"] and (now - cached["timestamp"]) < ENRICHED_DATA_TTL_SECONDS:
            missing = [t for t in tickers if t not in cached["data"] and not t.startswith("CD-") and t != "TBILL"]
            if not missing:
                return cached["data"]

        fresh_data = get_enriched_instrument_data(tickers)
        _enriched_data_cache["data"] = fresh_data
        _enriched_data_cache["timestamp"] = now
        return fresh_data