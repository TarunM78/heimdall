import os
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
import io, csv

from services.news_service import fetch_news_for_portfolio
from services.llm_analysis import analyze_news_batch, generate_overall_brief, generate_action_items
from services.portfolio_analytics import get_portfolio_analytics
from services.yfinance_service import get_portfolio_news, get_sector_weights, get_underrepresented_sectors, get_sector_news, get_ticker_movement
from services.constants import BENCHMARK_SECTOR_WEIGHTS

load_dotenv(override=True)

app = FastAPI(title="Heimdall API")

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
holdings_db: list[dict] = []

if os.path.exists("sample_data.csv"):
    with open("sample_data.csv", "r", encoding="utf-8") as f:
        content = f.read()
        if content.strip():
            # Support both tab and comma separation robustly
            lines = content.strip().split('\n')
            delims = '\t' if '\t' in lines[0] else ','
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delims)
            for row in reader:
                row = {k.strip().lower(): v.strip() for k, v in row.items()}
                ticker_key = next((k for k in row if "ticker" in k or "symbol" in k), None)
                if not ticker_key:
                    ticker_key = list(row.keys())[0] if row else None
                if not ticker_key or not row.get(ticker_key):
                    continue
                ticker = row[ticker_key].upper().strip()
                try:    qty        = float(row.get("qty") or row.get("quantity") or row.get("shares") or 0)
                except: qty = 0.0
                try:    cost_basis = float(row.get("cost_basis") or row.get("cost") or row.get("avg_cost") or 0)
                except: cost_basis = 0.0
                holdings_db.append({"ticker": ticker, "qty": qty, "cost_basis": cost_basis})

profile_db: dict = {
    "name": "",
    "risk_tolerance": "Moderate",
    "investment_horizon": "Long-term",
    "focus": [],
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class Holding(BaseModel):
    ticker: str
    qty: float = 0.0
    cost_basis: float = 0.0

class Portfolio(BaseModel):
    holdings: List[Holding]

class Profile(BaseModel):
    name: Optional[str] = ""
    risk_tolerance: Optional[str] = "Moderate"
    investment_horizon: Optional[str] = "Long-term"
    focus: Optional[List[str]] = []


# ---------------------------------------------------------------------------
# Portfolio endpoints
# ---------------------------------------------------------------------------
@app.get("/api/portfolio")
def get_portfolio():
    return {"holdings": holdings_db}

@app.post("/api/portfolio")
def update_portfolio(portfolio: Portfolio):
    global holdings_db
    seen, cleaned = set(), []
    for h in portfolio.holdings:
        t = h.ticker.upper().strip()
        if t and t not in seen:
            seen.add(t)
            cleaned.append({"ticker": t, "qty": h.qty, "cost_basis": h.cost_basis})
    holdings_db = cleaned
    return {"status": "success", "holdings": holdings_db}

@app.post("/api/portfolio/csv")
async def import_csv(file: UploadFile = File(...)):
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    imported = []
    for row in reader:
        row = {k.strip().lower(): v.strip() for k, v in row.items()}
        ticker_key = next((k for k in row if "ticker" in k or "symbol" in k), None)
        if not ticker_key:
            ticker_key = list(row.keys())[0] if row else None
        if not ticker_key or not row.get(ticker_key):
            continue
        ticker = row[ticker_key].upper().strip()
        try:    qty        = float(row.get("qty") or row.get("quantity") or row.get("shares") or 0)
        except: qty = 0.0
        try:    cost_basis = float(row.get("cost_basis") or row.get("cost") or row.get("avg_cost") or 0)
        except: cost_basis = 0.0
        existing = next((h for h in imported if h["ticker"] == ticker), None)
        if existing:
            existing["qty"] += qty
        else:
            imported.append({"ticker": ticker, "qty": qty, "cost_basis": cost_basis})
    if not imported:
        raise HTTPException(status_code=400, detail="No valid holdings found in CSV")
    for imp in imported:
        existing = next((h for h in holdings_db if h["ticker"] == imp["ticker"]), None)
        if existing:
            existing["qty"]        = imp["qty"]
            existing["cost_basis"] = imp["cost_basis"]
        else:
            holdings_db.append(imp)
    return {"status": "imported", "count": len(imported), "holdings": holdings_db}


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
@app.get("/api/analytics")
def analytics():
    if not holdings_db:
        return {"error": "No holdings"}
    try:
        return get_portfolio_analytics(holdings_db)
    except Exception as e:
        print(f"Analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Morning Brief (per-ticker)
# ---------------------------------------------------------------------------
@app.get("/api/brief")
async def generate_brief():
    if not holdings_db:
        return {"brief": []}
    tickers = [h["ticker"] for h in holdings_db]
    
    # Use yfinance exclusively by default
    ticker_news = []
    yf_news = await get_portfolio_news(tickers)
    for t, articles in yf_news.items():
        for article in articles:
            ticker_news.append({
                "ticker": t,
                "title": article.get("title", ""),
                "description": article.get("title", ""), # yf doesn't always have description, use title
                "url": article.get("link", ""),
                "source": article.get("publisher", ""),
            })

    if not ticker_news:
        return {"brief": []}
        
    # We pass an empty macro_news list since yfinance handles equities directly
    # Gather movements
    import asyncio
    movement_tasks = [get_ticker_movement(t) for t in tickers]
    movements_list = await asyncio.gather(*movement_tasks)
    movements_dict = {t: m for t, m in zip(tickers, movements_list)}
    
    try:
        return {"brief": analyze_news_batch(holdings_db, ticker_news, profile_db, macro_news=[], movements=movements_dict)}
    except Exception as e:
        print(f"Brief error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze news")


# ---------------------------------------------------------------------------
# Overall Brief (portfolio-wide synthesis)
# ---------------------------------------------------------------------------
@app.get("/api/overall_brief")
async def overall_brief():
    if not holdings_db:
        return {"error": "No holdings"}
    tickers = [h["ticker"] for h in holdings_db]
    
    # Use yfinance exclusively by default
    ticker_news = []
    yf_news = await get_portfolio_news(tickers)
    for t, articles in yf_news.items():
        for article in articles:
            ticker_news.append({
                "ticker": t,
                "title": article.get("title", ""),
                "description": article.get("title", ""),
                "url": article.get("link", ""),
                "source": article.get("publisher", ""),
            })

    try:
        analytic_data = get_portfolio_analytics(holdings_db)
    except Exception:
        analytic_data = {}
    try:
        result = generate_overall_brief(holdings_db, ticker_news, analytic_data, profile_db, macro_news=[])
        return result
    except Exception as e:
        print(f"Overall brief error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Actionable Items
# ---------------------------------------------------------------------------
@app.get("/api/actions")
def action_items():
    if not holdings_db:
        return {"items": []}
    try:
        analytic_data = get_portfolio_analytics(holdings_db)
        items = generate_action_items(holdings_db, analytic_data)
        return {"items": items}
    except Exception as e:
        print(f"Actions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# YFinance Data / Sector Gaps
# ---------------------------------------------------------------------------
@app.get("/api/portfolio/news")
async def fetch_portfolio_news():
    if not holdings_db:
        return {"news": {}}
    tickers = list({h["ticker"] for h in holdings_db})
    try:
        data = await get_portfolio_news(tickers)
        return {"news": data}
    except Exception as e:
        print(f"Portfolio news error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/portfolio/sector-gaps")
async def fetch_sector_gaps():
    if not holdings_db:
        return {"error": "No holdings"}
    tickers = list({h["ticker"] for h in holdings_db})
    try:
        portfolio_weights = await get_sector_weights(tickers)
        gaps = get_underrepresented_sectors(portfolio_weights)
        sector_news = await get_sector_news(gaps)
        
        return {
            "underrepresented_sectors": gaps,
            "sector_news": sector_news,
            "portfolio_weights": portfolio_weights,
            "benchmark_weights": BENCHMARK_SECTOR_WEIGHTS
        }
    except Exception as e:
        print(f"Sector gaps error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@app.get("/api/profile")
def get_profile():
    return profile_db

@app.post("/api/profile")
def update_profile(profile: Profile):
    profile_db.update(profile.model_dump(exclude_none=True))
    return {"status": "success", "profile": profile_db}


# ---------------------------------------------------------------------------
# Static files — mount LAST
# ---------------------------------------------------------------------------
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
