import asyncio
import csv
import json
from services.yfinance_service import get_portfolio_news

async def main():
    tickers = []
    with open("sample_data.csv", "r") as f:
        reader = csv.DictReader(f, delimiter='\t' if '\t' in f.read(100) else ',')
        f.seek(0)
        reader = csv.DictReader(f, delimiter='\t' if '\t' in f.read(100) else ',')
        f.seek(0)
        content = f.read().strip().split('\n')
        delims = '\t' if '\t' in content[0] else ','
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delims)
        
        for row in reader:
            row = {k.strip().lower(): v.strip() for k, v in row.items()}
            ticker_key = next((k for k in row if "ticker" in k or "symbol" in k), None)
            if ticker_key and row.get(ticker_key):
                tickers.append(row[ticker_key].upper().strip())

    print(f"Loaded tickers: {tickers}")
    news_data = await get_portfolio_news(tickers)
    
    with open("yfinance_debug_pull.txt", "w", encoding="utf-8") as f:
        f.write("# YFinance News Debug Log\n")
        f.write("="*60 + "\n\n")
        for ticker, articles in news_data.items():
            f.write(f"--- TICKER: {ticker} ---\n")
            if not articles:
                f.write("  No news found.\n")
            for article in articles:
                f.write(f"  Title: {article.get('title', 'N/A')}\n")
                f.write(f"  Link:  {article.get('link', 'N/A')}\n")
                f.write(f"  Pub:   {article.get('publisher', 'N/A')}\n")
                f.write("\n")
            f.write("\n")

if __name__ == "__main__":
    asyncio.run(main())
