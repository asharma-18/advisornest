import yfinance as yf
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# ── Curated instrument lists by risk ─────────────────────
STOCKS_LONG_TERM = {
    "low":    ["VTI", "VOO", "SCHD", "VYM", "BRK-B"],
    "medium": ["VOO", "VTI", "MSFT", "AAPL", "JNJ"],
    "high":   ["MSFT", "AAPL", "NVDA", "GOOGL", "AMZN"]
}

STOCKS_SHORT_TERM = {
    "low":    ["VIG", "NOBL", "SDY"],
    "medium": ["QQQ", "SPY", "META", "TSLA"],
    "high":   ["NVDA", "META", "TSLA", "AMD", "ARKK"]
}

BONDS = {
    "low":    ["BND", "AGG", "MUB", "TIP"],
    "medium": ["BND", "AGG", "TLT", "LQD"],
    "high":   ["HYG", "JNK", "TLT", "EMB"]
}

MUTUAL_FUNDS = {
    "low":    ["VFIAX", "VBTLX", "VWELX"],
    "medium": ["VFIAX", "FXAIX", "VWELX"],
    "high":   ["FXAIX", "FOCPX", "VIMAX"]
}


# ── Fetch stock data ──────────────────────────────────────
def get_stock_data(risk, category="long"):
    risk = risk.lower()

    if category == "long":
        tickers = STOCKS_LONG_TERM.get(risk, STOCKS_LONG_TERM["medium"])
    elif category == "short":
        tickers = STOCKS_SHORT_TERM.get(risk, STOCKS_SHORT_TERM["medium"])
    elif category == "bonds":
        tickers = BONDS.get(risk, BONDS["medium"])
    else:
        tickers = MUTUAL_FUNDS.get(risk, MUTUAL_FUNDS["medium"])

    results = []
    for ticker in tickers:
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

            results.append({
                "ticker":         ticker,
                "name":           name,
                "price":          round(price, 2) if price else "N/A",
                "pe_ratio":       round(pe, 1) if pe else "N/A",
                "dividend_yield": f"{round(div_yield * 100, 2)}%" if div_yield and div_yield < 1 else f"{round(div_yield, 2)}%" if div_yield else "N/A",
                "52w_high":       round(week52_high, 2) if week52_high else "N/A",
                "52w_low":        round(week52_low, 2) if week52_low else "N/A",
                "expense_ratio":  f"{round(expense * 100, 2)}%" if expense else "N/A",
            })

        except Exception:
            results.append({
                "ticker":         ticker,
                "name":           ticker,
                "price":          "N/A",
                "pe_ratio":       "N/A",
                "dividend_yield": "N/A",
                "52w_high":       "N/A",
                "52w_low":        "N/A",
                "expense_ratio":  "N/A",
            })

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
    return {
        "stocks_lt":    get_stock_data(risk, "long"),
        "stocks_st":    get_stock_data(risk, "short"),
        "bonds":        get_stock_data(risk, "bonds"),
        "mutual_funds": get_stock_data(risk, "mutual"),
        "rates":        get_rates()
    }