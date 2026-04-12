import os
import requests
from datetime import datetime, timedelta


MACRO_QUERIES = [
    "Federal Reserve interest rates inflation",
    "CPI PPI GDP economic data",
    "US tariffs trade war China",
    "geopolitical Iran war Middle East",
    "treasury yields bond market",
    "Trump economic policy",
]


def fetch_news_for_portfolio(tickers: list[str]) -> dict:
    """
    Returns a dict with:
      - 'ticker_news': list of {ticker, title, description, source}
      - 'macro_news':  list of {title, description, source}
    """
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        print("Warning: NEWSAPI_KEY not set.")
        return {"ticker_news": [], "macro_news": []}

    from_date = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
    ticker_news = []
    macro_news  = []

    # ---- Per-ticker news ----
    for ticker in tickers:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": f"{ticker} stock OR {ticker} earnings OR {ticker} revenue OR {ticker} company",
            "from": from_date,
            "sortBy": "relevancy",
            "language": "en",
            "apiKey": api_key,
            "pageSize": 5,
        }
        try:
            resp = requests.get(url, params=params, timeout=8)
            data = resp.json()
            if data.get("status") == "ok":
                for article in data.get("articles", []):
                    ticker_news.append({
                        "ticker": ticker,
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "url": article.get("url"),
                        "source": article.get("source", {}).get("name", ""),
                    })
        except Exception as e:
            print(f"Error fetching news for {ticker}: {e}")

    # ---- Macro / geopolitical news ----
    seen_titles: set[str] = set()
    for query in MACRO_QUERIES:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "from": from_date,
            "sortBy": "relevancy",
            "language": "en",
            "apiKey": api_key,
            "pageSize": 3,
        }
        try:
            resp = requests.get(url, params=params, timeout=8)
            data = resp.json()
            if data.get("status") == "ok":
                for article in data.get("articles", []):
                    title = article.get("title", "")
                    key = title[:60]
                    if key and key not in seen_titles:
                        seen_titles.add(key)
                        macro_news.append({
                            "title": title,
                            "description": article.get("description", ""),
                            "source": article.get("source", {}).get("name", ""),
                        })
        except Exception as e:
            print(f"Error fetching macro news ({query}): {e}")

    return {"ticker_news": ticker_news, "macro_news": macro_news}
