import asyncio
import logging
from typing import List, Dict
import yfinance as yf
from cachetools import TTLCache
from .constants import BENCHMARK_SECTOR_WEIGHTS, SECTOR_ETF_MAP

logger = logging.getLogger(__name__)

# Cache valid for 30 minutes (max 100 items for memory safety)
NEWS_CACHE = TTLCache(maxsize=100, ttl=1800)
WEIGHTS_CACHE = TTLCache(maxsize=100, ttl=3600)  # Sector weights change slowly

def _fetch_yf_news(ticker: str) -> List[Dict]:
    """Synchronous function to fetch and clean yfinance news."""
    try:
        t = yf.Ticker(ticker)
        raw_news = t.news
        cleaned = []
        if isinstance(raw_news, list):
            for item in raw_news:
                # yfinance API returns a nested 'content' dictionary
                content = item.get("content", {})
                title = content.get("title", item.get("title", "No Title"))
                
                # Link is often buried in canonicalUrl or clickThroughUrl
                canonical = content.get("canonicalUrl", {})
                link = canonical.get("url", item.get("link", "#"))
                
                # Publisher
                provider = content.get("provider", {})
                publisher = provider.get("displayName", item.get("publisher", "Unknown"))
                
                published_at = content.get("pubDate", item.get("providerPublishTime", 0))

                cleaned.append({
                    "title": title,
                    "link": link,
                    "publisher": publisher,
                    "published_at": published_at
                })
        return cleaned
    except Exception as e:
        logger.error(f"Error fetching news for {ticker}: {e}")
        return []

async def get_ticker_news(ticker: str) -> List[Dict]:
    """Async wrapper for fetching news for a single ticker."""
    if ticker in NEWS_CACHE:
        return NEWS_CACHE[ticker]
    
    news = await asyncio.to_thread(_fetch_yf_news, ticker)
    if news:
        NEWS_CACHE[ticker] = news
    return news

async def get_portfolio_news(tickers: List[str]) -> Dict[str, List[Dict]]:
    """Fetch news for multiple tickers, maintaining rate boundaries."""
    results = {}
    for ticker in tickers:
        results[ticker] = await get_ticker_news(ticker)
        # Sleep to avoid rapid-fire yfinance throttling when querying many tickers
        await asyncio.sleep(0.3)
    return results

def _fetch_yf_sector(ticker: str) -> str:
    """Synchronous function to fetch the sector for a ticker."""
    try:
        t = yf.Ticker(ticker)
        return t.info.get("sector", "Unknown")
    except Exception as e:
        logger.error(f"Error fetching sector for {ticker}: {e}")
        return "Unknown"

def _fetch_yf_movement(ticker: str) -> float:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if len(hist) >= 2:
            change = (hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]
            return round(change * 100, 2)
        return 0.0
    except Exception:
        return 0.0

async def get_ticker_movement(ticker: str) -> float:
    return await asyncio.to_thread(_fetch_yf_movement, ticker)

async def get_sector_weights(tickers: List[str]) -> Dict[str, float]:
    """Calculates percentage weight participation of sectors within the exact ticker list."""
    if not tickers:
        return {}
    
    sectors = {}
    for ticker in tickers:
        if ticker in WEIGHTS_CACHE:
            s_name = WEIGHTS_CACHE[ticker]
        else:
            s_name = await asyncio.to_thread(_fetch_yf_sector, ticker)
            WEIGHTS_CACHE[ticker] = s_name
            await asyncio.sleep(0.3)
            
        sectors[s_name] = sectors.get(s_name, 0) + 1

    total = sum(sectors.values())
    if total == 0:
        return {}
        
    return {k: round(v / total, 3) for k, v in sectors.items()}

def get_underrepresented_sectors(portfolio_sectors: Dict[str, float], benchmark_sectors: Dict[str, float] = None, threshold: float = 0.05) -> List[str]:
    """Identify sectors where the portfolio allocation is below the benchmark by `threshold`."""
    if benchmark_sectors is None:
        benchmark_sectors = BENCHMARK_SECTOR_WEIGHTS

    underrepresented = []
    
    for sector, b_weight in benchmark_sectors.items():
        p_weight = portfolio_sectors.get(sector, 0.0)
        
        # If the portfolio is missing it entirely (or severely) compared to benchmark minus threshold.
        if (b_weight - p_weight) >= threshold:
            underrepresented.append(sector)
            
    return underrepresented

async def get_sector_news(sectors: List[str]) -> Dict[str, List[Dict]]:
    """Map sectors to ETFs and fetch news."""
    results = {}
    for sector in sectors:
        etf_ticker = SECTOR_ETF_MAP.get(sector)
        if etf_ticker:
            results[sector] = await get_ticker_news(etf_ticker)
            await asyncio.sleep(0.3)
    return results
