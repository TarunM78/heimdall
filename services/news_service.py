import os
import requests
from datetime import datetime, timedelta

def fetch_news_for_portfolio(tickers: list[str]) -> list[dict]:
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        print("Warning: NEWSAPI_KEY not set.")
        return []

    # Calculate date for the last 48 hours for fresh news
    from_date = (datetime.utcnow() - timedelta(days=2)).strftime('%Y-%m-%d')
    
    all_articles = []
    
    # We will fetch a few articles per ticker to keep things brief
    for ticker in tickers:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": f"{ticker} stock OR {ticker} crypto OR {ticker} company",
            "from": from_date,
            "sortBy": "relevancy",
            "language": "en",
            "apiKey": api_key,
            "pageSize": 3  # top 3 per ticker
        }
        
        try:
            resp = requests.get(url, params=params)
            data = resp.json()
            if data.get("status") == "ok":
                for article in data.get("articles", []):
                    all_articles.append({
                        "ticker": ticker,
                        "title": article.get("title"),
                        "description": article.get("description"),
                        "url": article.get("url"),
                        "source": article.get("source", {}).get("name")
                    })
        except Exception as e:
            print(f"Error fetching news for {ticker}: {e}")

    return all_articles
