import typing_extensions
if not hasattr(typing_extensions, "Sentinel"):
    class Sentinel:
        def __repr__(self) -> str:
            return "Sentinel"
    typing_extensions.Sentinel = Sentinel()

import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
import io, csv
import jwt
import requests

from services.yfinance_service import get_portfolio_news, get_sector_weights, get_underrepresented_sectors, get_sector_news, get_ticker_movement
from services.constants import BENCHMARK_SECTOR_WEIGHTS
from services.llm_analysis import analyze_news_batch, generate_overall_brief, generate_action_items
from services.portfolio_analytics import get_portfolio_analytics
from services.snaptrade_service import snaptrade_service
from services.tts_service import generate_speech_stream

load_dotenv(override=True)

app = FastAPI(title="Heimdall API")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ---------------------------------------------------------------------------
# Auth0 Configuration
# ---------------------------------------------------------------------------
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_CLIENT_ID = os.getenv("AUTH0_CLIENT_ID")

# ---------------------------------------------------------------------------
# In-memory stores (Per-user)
# ---------------------------------------------------------------------------
# user_id -> list[dict]
holdings_db: dict[str, list[dict]] = {}
# user_id -> dict
profile_db: dict[str, dict] = {}
# user_id -> dict { "snaptrade_user_id": ..., "snaptrade_user_secret": ... }
snaptrade_db: dict[str, dict] = {}

DEFAULT_PROFILE = {
    "name": "",
    "risk_tolerance": "Moderate",
    "investment_horizon": "Long-term",
    "focus": [],
}

def get_user_data(user_id: str):
    if user_id not in holdings_db:
        holdings_db[user_id] = []
    if user_id not in profile_db:
        profile_db[user_id] = DEFAULT_PROFILE.copy()
    return holdings_db[user_id], profile_db[user_id]

# ---------------------------------------------------------------------------
# Auth Dependency
# ---------------------------------------------------------------------------
async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        # For development/demo purposes, we could return a default user
        # but the request asked to remove fake auth.
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    try:
        token = authorization.split(" ")[1]
        # In a real production app, you would verify the JWT signature here.
        # For this implementation, we will decode and trust the 'sub' claim
        # to identify the user, keeping the logic clean and minimal as requested.
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
        except Exception as e:
            # Include token info for debugging
            token_info = f"len={len(token)}"
            if len(token) > 10:
                token_info += f", prefix={token[:10]}..."
            raise HTTPException(status_code=401, detail=f"Token decoding failed ({token_info}): {str(e)}")
            
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: 'sub' claim missing")
        return user_id
    except IndexError:
        raise HTTPException(status_code=401, detail="Malformed Authorization header. Expected 'Bearer <token>'")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

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

class TTSRequest(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# Auth Config Endpoint
# ---------------------------------------------------------------------------
@app.get("/api/auth/config")
def auth_config():
    return {
        "domain": AUTH0_DOMAIN,
        "clientId": AUTH0_CLIENT_ID
    }


# ---------------------------------------------------------------------------
# Portfolio endpoints
# ---------------------------------------------------------------------------
@app.get("/api/portfolio")
def get_portfolio(user_id: str = Depends(get_current_user)):
    holdings, _ = get_user_data(user_id)
    return {"holdings": holdings}

@app.post("/api/portfolio")
def update_portfolio(portfolio: Portfolio, user_id: str = Depends(get_current_user)):
    holdings, _ = get_user_data(user_id)
    seen, cleaned = set(), []
    for h in portfolio.holdings:
        t = h.ticker.upper().strip()
        if t and t not in seen:
            seen.add(t)
            cleaned.append({"ticker": t, "qty": h.qty, "cost_basis": h.cost_basis})
    holdings_db[user_id] = cleaned
    return {"status": "success", "holdings": cleaned}

@app.post("/api/portfolio/csv")
async def import_csv(file: UploadFile = File(...), user_id: str = Depends(get_current_user)):
    holdings, _ = get_user_data(user_id)
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
        existing = next((h for h in holdings if h["ticker"] == imp["ticker"]), None)
        if existing:
            existing["qty"]        = imp["qty"]
            existing["cost_basis"] = imp["cost_basis"]
        else:
            holdings.append(imp)
    
    return {"status": "imported", "count": len(imported), "holdings": holdings}


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
@app.get("/api/analytics")
def analytics(user_id: str = Depends(get_current_user)):
    holdings, _ = get_user_data(user_id)
    if not holdings:
        return {"error": "No holdings"}
    try:
        return get_portfolio_analytics(holdings)
    except Exception as e:
        print(f"Analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Morning Brief (per-ticker)
# ---------------------------------------------------------------------------
@app.get("/api/brief")
async def generate_brief(user_id: str = Depends(get_current_user)):
    holdings, profile = get_user_data(user_id)
    if not holdings:
        return {"brief": []}
    tickers = [h["ticker"] for h in holdings]
    
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
        return {"brief": analyze_news_batch(holdings, ticker_news, profile, macro_news=[], movements=movements_dict)}
    except Exception as e:
        print(f"Brief error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze news")


# ---------------------------------------------------------------------------
# Overall Brief (portfolio-wide synthesis)
# ---------------------------------------------------------------------------
@app.get("/api/overall_brief")
async def overall_brief(user_id: str = Depends(get_current_user)):
    holdings, profile = get_user_data(user_id)
    if not holdings:
        return {"error": "No holdings"}
    tickers = [h["ticker"] for h in holdings]
    
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
        analytic_data = get_portfolio_analytics(holdings)
    except Exception:
        analytic_data = {}
    try:
        result = generate_overall_brief(holdings, ticker_news, analytic_data, profile, macro_news=[])
        return result
    except Exception as e:
        print(f"Overall brief error: {e}")
        raise HTTPException(status_code=500, detail="Failed to synthesize brief")


# ---------------------------------------------------------------------------
# Actionable Items
# ---------------------------------------------------------------------------
@app.get("/api/actions")
def action_items(user_id: str = Depends(get_current_user)):
    holdings, _ = get_user_data(user_id)
    if not holdings:
        return {"items": []}
    try:
        analytic_data = get_portfolio_analytics(holdings)
        items = generate_action_items(holdings, analytic_data)
        return {"items": items}
    except Exception as e:
        print(f"Actions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# YFinance Data / Sector Gaps
# ---------------------------------------------------------------------------
@app.get("/api/portfolio/news")
async def fetch_portfolio_news(user_id: str = Depends(get_current_user)):
    holdings, _ = get_user_data(user_id)
    if not holdings:
        return {"news": {}}
    tickers = list({h["ticker"] for h in holdings})
    try:
        data = await get_portfolio_news(tickers)
        return {"news": data}
    except Exception as e:
        print(f"Portfolio news error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/portfolio/sector-gaps")
async def fetch_sector_gaps(user_id: str = Depends(get_current_user)):
    holdings, _ = get_user_data(user_id)
    if not holdings:
        return {"error": "No holdings"}
    tickers = list({h["ticker"] for h in holdings})
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
# TTS Briefing
# ---------------------------------------------------------------------------
@app.post("/api/tts")
async def text_to_speech(req: TTSRequest, user_id: str = Depends(get_current_user)):
    def iterfile():
        for chunk in generate_speech_stream(req.text):
            yield chunk
    return StreamingResponse(iterfile(), media_type="audio/mpeg")

# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@app.get("/api/profile")
def get_profile(user_id: str = Depends(get_current_user)):
    _, profile = get_user_data(user_id)
    return profile

@app.post("/api/profile")
def update_profile(profile_update: Profile, user_id: str = Depends(get_current_user)):
    _, profile = get_user_data(user_id)
    profile.update(profile_update.model_dump(exclude_none=True))
    return {"status": "success", "profile": profile}


# ---------------------------------------------------------------------------
# SnapTrade Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/snaptrade/status")
def snaptrade_status(user_id: str = Depends(get_current_user)):
    user_cred = snaptrade_db.get(user_id)
    
    # Check for test override (e.g. for user 'Jeremy')
    test_uid = os.getenv("SNAPTRADE_TEST_USER_ID")
    test_sec = os.getenv("SNAPTRADE_TEST_USER_SECRET")
    
    if test_uid and test_sec and not user_cred:
        user_cred = {
            "snaptrade_user_id": test_uid,
            "snaptrade_user_secret": test_sec
        }
        snaptrade_db[user_id] = user_cred

    return {
        "connected": bool(user_cred and user_cred.get("snaptrade_user_secret")),
        "snaptrade_user_id": user_cred.get("snaptrade_user_id") if user_cred else None
    }

@app.post("/api/snaptrade/connect")
def snaptrade_connect(user_id: str = Depends(get_current_user)):
    # Check if SnapTrade keys are configured
    client_id = os.getenv("SNAPTRADE_CLIENT_ID")
    if not client_id or "replace_with" in client_id:
        raise HTTPException(
            status_code=400, 
            detail="SnapTrade is not configured. Please add your credentials to the .env file."
        )

    user_cred = snaptrade_db.get(user_id)
    
    if not user_cred:
        # Register new SnapTrade user
        # We use a prefixed version of Auth0 sub as SnapTrade user_id
        st_user_id = f"heimdall_{user_id.replace('|', '_')}"
        res = snaptrade_service.register_user(st_user_id)
        user_cred = {
            "snaptrade_user_id": st_user_id,
            "snaptrade_user_secret": res.get("userSecret")
        }
        snaptrade_db[user_id] = user_cred

    # Generate portal URL
    redirect_uri = os.getenv("AUTH0_CALLBACK_URL", "http://127.0.0.1:8000/")
    portal_url = snaptrade_service.get_login_url(
        user_cred["snaptrade_user_id"], 
        user_cred["snaptrade_user_secret"],
        redirect_uri
    )
    return {"portal_url": portal_url}

@app.post("/api/snaptrade/sync")
def snaptrade_sync(user_id: str = Depends(get_current_user)):
    user_cred = snaptrade_db.get(user_id)
    if not user_cred or not user_cred.get("snaptrade_user_secret"):
        raise HTTPException(status_code=400, detail="SnapTrade not connected")
    
    try:
        st_holdings = snaptrade_service.fetch_holdings(
            user_cred["snaptrade_user_id"],
            user_cred["snaptrade_user_secret"]
        )
        
        # Merge with existing holdings_db
        # Tickers from SnapTrade replace existing ones in our db
        local_holdings = holdings_db.get(user_id, [])
        new_holdings = {h["ticker"]: h for h in local_holdings}
        
        for st_h in st_holdings:
            new_holdings[st_h["ticker"]] = st_h
            
        holdings_db[user_id] = list(new_holdings.values())
        return {"status": "synced", "count": len(st_holdings), "holdings": holdings_db[user_id]}
    except Exception as e:
        print(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync with SnapTrade")

@app.delete("/api/snaptrade/disconnect")
def snaptrade_disconnect(user_id: str = Depends(get_current_user)):
    if user_id in snaptrade_db:
        del snaptrade_db[user_id]
    return {"status": "disconnected"}


# ---------------------------------------------------------------------------
# Static files — mount LAST
# ---------------------------------------------------------------------------
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
