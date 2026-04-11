import os
import io
import csv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

from services.news_service import fetch_news_for_portfolio
from services.llm_analysis import analyze_news_batch
from services.portfolio_analytics import get_portfolio_analytics

load_dotenv(override=True)

app = FastAPI(title="Heimdall API")

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
# Holdings: list of { ticker, qty, cost_basis }
holdings_db: list[dict] = []

# User profile
profile_db: dict = {
    "name": "",
    "risk_tolerance": "Moderate",  # Conservative | Moderate | Aggressive
    "investment_horizon": "Long-term",
    "focus": [],  # e.g. ["tech", "crypto"]
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class Holding(BaseModel):
    ticker: str
    qty: float = 0.0
    cost_basis: float = 0.0   # average cost per share/unit


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
    seen = set()
    cleaned = []
    for h in portfolio.holdings:
        t = h.ticker.upper().strip()
        if t and t not in seen:
            seen.add(t)
            cleaned.append({"ticker": t, "qty": h.qty, "cost_basis": h.cost_basis})
    holdings_db = cleaned
    return {"status": "success", "holdings": holdings_db}


@app.post("/api/portfolio/csv")
async def import_csv(file: UploadFile = File(...)):
    """
    Accept a CSV with columns: ticker, qty, cost_basis (header row required).
    Also supports simpler 1-column CSVs (ticker only) exported from brokers.
    """
    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    
    global holdings_db
    imported = []
    errors = []
    
    for i, row in enumerate(reader):
        # normalise header names (case-insensitive, strip spaces)
        row = {k.strip().lower(): v.strip() for k, v in row.items()}
        
        ticker_key = next((k for k in row if "ticker" in k or "symbol" in k), None)
        if not ticker_key:
            # try first column
            ticker_key = list(row.keys())[0] if row else None
        
        if not ticker_key or not row.get(ticker_key):
            continue
        
        ticker = row[ticker_key].upper().strip()
        try:
            qty = float(row.get("qty") or row.get("quantity") or row.get("shares") or 0)
        except ValueError:
            qty = 0.0
        try:
            cost_basis = float(row.get("cost_basis") or row.get("cost") or row.get("avg_cost") or 0)
        except ValueError:
            cost_basis = 0.0
        
        # dedup
        existing = next((h for h in imported if h["ticker"] == ticker), None)
        if existing:
            existing["qty"] += qty
        else:
            imported.append({"ticker": ticker, "qty": qty, "cost_basis": cost_basis})
    
    if not imported:
        raise HTTPException(status_code=400, detail="No valid holdings found in CSV")
    
    # Merge with existing (don't wipe)
    for imp in imported:
        existing = next((h for h in holdings_db if h["ticker"] == imp["ticker"]), None)
        if existing:
            existing["qty"] = imp["qty"]
            existing["cost_basis"] = imp["cost_basis"]
        else:
            holdings_db.append(imp)
    
    return {"status": "imported", "count": len(imported), "holdings": holdings_db}


# ---------------------------------------------------------------------------
# Portfolio Analytics (yfinance)
# ---------------------------------------------------------------------------
@app.get("/api/analytics")
def analytics():
    if not holdings_db:
        return {"error": "No holdings"}
    tickers = [h["ticker"] for h in holdings_db]
    try:
        result = get_portfolio_analytics(holdings_db)
        return result
    except Exception as e:
        print(f"Analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Morning Brief
# ---------------------------------------------------------------------------
@app.get("/api/brief")
def generate_brief():
    if not holdings_db:
        return {"brief": []}
    tickers = [h["ticker"] for h in holdings_db]
    raw_news = fetch_news_for_portfolio(tickers)
    if not raw_news:
        return {"brief": []}
    try:
        analyzed = analyze_news_batch(holdings_db, raw_news, profile_db)
        return {"brief": analyzed}
    except Exception as e:
        print(f"Error in LLM analysis: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze news")


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
# Static files (Frontend) — mount LAST
# ---------------------------------------------------------------------------
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
