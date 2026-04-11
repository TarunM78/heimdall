import os
import json
from openai import OpenAI


TOOLTIPS = {}  # not used here but keep imports clean


def _get_client():
    api_key = os.getenv("FEATHERLESS_API_KEY")
    base_url = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
    model = os.getenv("FEATHERLESS_MODEL", "NousResearch/Meta-Llama-3-8B-Instruct")
    return OpenAI(api_key=api_key, base_url=base_url), model


def _parse_json(raw: str) -> dict:
    """Strip markdown fences and extract the first JSON object."""
    raw = raw.strip().strip("`")
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start >= 0 and end > start:
        raw = raw[start:end]
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Per-ticker analysis
# ---------------------------------------------------------------------------
def analyze_news_batch(holdings: list[dict], news_batch: list[dict], profile: dict) -> list[dict]:
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key or api_key == "replace_with_your_featherless_key":
        return mock_fallback(holdings)

    client, model = _get_client()

    # Group news by ticker
    news_by_ticker: dict[str, list[str]] = {}
    for item in news_batch:
        t = item["ticker"]
        news_by_ticker.setdefault(t, [])
        title = item.get("title") or ""
        desc  = item.get("description") or ""
        if title:
            news_by_ticker[t].append(f"• {title}. {desc}".strip())

    risk     = profile.get("risk_tolerance", "Moderate")
    horizon  = profile.get("investment_horizon", "Long-term")

    results = []

    for holding in holdings:
        ticker     = holding["ticker"]
        qty        = holding.get("qty", 0)
        cost_basis = holding.get("cost_basis", 0)
        articles   = news_by_ticker.get(ticker, [])

        if not articles:
            continue

        articles_text = "\n".join(articles[:6])

        position_ctx = ""
        if qty and cost_basis:
            position_ctx = f"Position: {qty} units at avg cost ${cost_basis:.2f}."
        elif qty:
            position_ctx = f"Position: {qty} units (no cost basis provided)."

        prompt = f"""You are Heimdall, a sharp institutional-grade financial analyst. Be specific, data-driven, and insightful — no generic platitudes.

USER CONTEXT:
- Ticker: {ticker}
- {position_ctx}
- Risk tolerance: {risk} | Investment horizon: {horizon}

RECENT NEWS:
{articles_text}

TASK: Analyze the above news and produce a precise, actionable assessment. Be specific about:
1. What EXACTLY changed or happened (prices, percentages, product names, competitors, macro data)
2. The MECHANISM of impact (e.g. "higher rates compress growth multiples", "supply glut pressures margins", "beats consensus by X%")
3. What this means for THIS specific position — considering the entry price vs current environment

OUTPUT: Respond ONLY with a valid raw JSON object. No markdown. No preamble. Exactly this structure:
{{
  "ticker": "{ticker}",
  "headline": "One punchy sentence with a specific fact or figure from the news.",
  "bullets": [
    "Specific development 1 with concrete detail (% move, dollar figure, comparison)",
    "Specific development 2",
    "Key risk or tailwind to watch"
  ],
  "sentiment": "Bullish" or "Bearish" or "Neutral",
  "impact": "High" or "Medium" or "Low",
  "key_drivers": ["driver with specifics", "driver 2"],
  "position_insight": "2 sentences max. Explain the specific mechanism: what happened → why it matters → concrete implication for this position at this cost basis / timeframe. Name actual numbers, ratios, or catalysts.",
  "action_signal": "Monitor" or "Review" or "Act"
}}"""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Output ONLY raw JSON, no markdown, no explanations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.15,
                max_tokens=500,
            )
            parsed = _parse_json(response.choices[0].message.content)
            parsed["ticker"]     = ticker
            parsed["qty"]        = qty
            parsed["cost_basis"] = cost_basis
            results.append(parsed)

        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            results.append(_error_card(ticker, qty, cost_basis))

    return results


# ---------------------------------------------------------------------------
# Portfolio-wide overall brief
# ---------------------------------------------------------------------------
def generate_overall_brief(holdings: list[dict], news_batch: list[dict],
                            analytics: dict, profile: dict) -> dict:
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key or api_key == "replace_with_your_featherless_key":
        return mock_overall(holdings, analytics)

    client, model = _get_client()

    tickers = [h["ticker"] for h in holdings]
    risk    = profile.get("risk_tolerance", "Moderate")
    horizon = profile.get("investment_horizon", "Long-term")
    name    = profile.get("name") or "Investor"

    # Flatten top news per ticker
    news_lines = []
    seen = set()
    for item in news_batch:
        key = item.get("title", "")[:60]
        if key not in seen:
            seen.add(key)
            news_lines.append(f"[{item['ticker']}] {item.get('title','')}. {item.get('description','')[:100]}")

    # Analytics context
    m   = analytics.get("portfolio_metrics", {})
    div = analytics.get("diversification", {})
    metrics_ctx = ""
    if m.get("sharpe_ratio") is not None:
        metrics_ctx = f"Portfolio Sharpe: {m['sharpe_ratio']}, Annualised vol: {m.get('annual_volatility_pct','?')}%, est. annual return: {m.get('annual_return_pct','?')}%. Diversification: {div.get('label','?')} (score {div.get('score','?')}/100)."

    flags = div.get("flags", [])
    flags_ctx = " | ".join(flags) if flags else "No major concentration warnings."

    news_text = "\n".join(news_lines[:15])

    prompt = f"""You are Heimdall, an AI financial advisor writing a morning brief for {name}.

PORTFOLIO: {', '.join(tickers)}
RISK PROFILE: {risk} | Horizon: {horizon}
{metrics_ctx}
PORTFOLIO FLAGS: {flags_ctx}

LATEST NEWS ACROSS PORTFOLIO:
{news_text}

Write a concise, insightful morning portfolio brief — like a note from a sharp hedge fund PM.
Format:
- Start with a 1-sentence BLUF (Bottom Line Up Front) about the portfolio outlook today.
- 3-5 key points: each must reference a specific ticker or macro theme with concrete detail.
- Close with 1-sentence on the biggest risk or opportunity to watch.

Tone: Direct, professional, no fluff. No "it's important to..." or "consider monitoring..." — give actual analysis.
Do not use bullet-point formatting — write in short readable paragraphs.
Respond ONLY with raw JSON:
{{
  "bluf": "One punchy portfolio-wide takeaway sentence.",
  "body": "3-5 paragraph morning note. Specific, named, data-driven.",
  "portfolio_sentiment": "Bullish" or "Bearish" or "Mixed",
  "watch_item": "The single most important thing to monitor today."
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a financial analyst writing morning briefings. Output ONLY raw JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.25,
            max_tokens=600,
        )
        parsed = _parse_json(response.choices[0].message.content)
        return parsed
    except Exception as e:
        print(f"Overall brief error: {e}")
        return mock_overall(holdings, analytics)


# ---------------------------------------------------------------------------
# Actionable items (rule-based, no LLM needed)
# ---------------------------------------------------------------------------
def generate_action_items(holdings: list[dict], analytics: dict) -> list[dict]:
    items = []
    total = analytics.get("total_value", 0)
    div   = analytics.get("diversification", {})
    hs    = analytics.get("holdings", [])
    m     = analytics.get("portfolio_metrics", {})

    # 1. Concentration check
    for h in hs:
        if h.get("weight_pct", 0) > 40:
            items.append({
                "type": "danger",
                "icon": "⚖️",
                "title": f"{h['ticker']} is overweight at {h['weight_pct']:.0f}% of portfolio",
                "sub": "Consider trimming to reduce single-stock concentration risk. Conventional guidance suggests no single position >20–25%."
            })
        elif h.get("weight_pct", 0) > 25:
            items.append({
                "type": "warning",
                "icon": "📊",
                "title": f"{h['ticker']} is {h['weight_pct']:.0f}% of portfolio — watch sizing",
                "sub": "Position is getting large. If this thesis breaks, it will meaningfully hurt returns."
            })

    # 2. Sector concentration
    sectors = div.get("sector_breakdown", {})
    for sector, pct in sectors.items():
        if sector not in ("Unknown", "Crypto") and pct > 55:
            items.append({
                "type": "warning",
                "icon": "🏭",
                "title": f"High sector concentration — {sector} is {pct:.0f}% of portfolio",
                "sub": "Sector-specific shocks (regulation, commodity prices, rate sensitivity) could hit your portfolio hard. Consider adding exposure to other sectors."
            })

    # 3. Sharpe ratio
    sharpe = m.get("sharpe_ratio")
    if sharpe is not None:
        if sharpe < 0:
            items.append({
                "type": "danger",
                "icon": "📉",
                "title": f"Portfolio Sharpe ratio is negative ({sharpe})",
                "sub": "You are bearing risk without being compensated with returns vs the risk-free rate. Review your highest-volatility positions."
            })
        elif sharpe < 0.5:
            items.append({
                "type": "warning",
                "icon": "📉",
                "title": f"Low risk-adjusted returns — Sharpe of {sharpe}",
                "sub": "A Sharpe below 0.5 means returns are poor relative to the volatility you're taking on. The S&P 500 historically runs ~0.5–1.0."
            })
        elif sharpe > 1.5:
            items.append({
                "type": "success",
                "icon": "🌟",
                "title": f"Strong risk-adjusted returns — Sharpe of {sharpe}",
                "sub": "Excellent! This means you're generating good returns per unit of risk. Keep this portfolio composition in mind."
            })

    # 4. Missing sector exposure (simple heuristic)
    covered_sectors = set(s.lower() for s in sectors.keys())
    if not any("energy" in s or "utilities" in s for s in covered_sectors):
        items.append({
            "type": "info",
            "icon": "💡",
            "title": "No energy or utilities exposure",
            "sub": "Energy and utilities can act as inflation hedges and reduce correlation to tech/growth stocks. Consider adding XLE (Energy ETF) or XLU (Utilities ETF)."
        })
    if not any("health" in s for s in covered_sectors):
        items.append({
            "type": "info",
            "icon": "💡",
            "title": "No healthcare exposure",
            "sub": "Healthcare is defensive in downturns and benefits from demographic tailwinds. Consider XLV or individual pharma/biotech exposure."
        })

    # 5. Underwater positions
    for h in hs:
        if h.get("gain_pct", 0) < -20 and h.get("qty", 0):
            items.append({
                "type": "warning",
                "icon": "🔴",
                "title": f"{h['ticker']} is down {abs(h['gain_pct']):.1f}% from your cost basis",
                "sub": f"At ${h.get('current_price','?'):.2f} vs your avg cost of ${h.get('cost_basis','?'):.2f}. Evaluate whether the original thesis still holds, or if this is a tax-loss harvesting opportunity."
            })

    # 6. No diversification
    if len(holdings) < 3:
        items.append({
            "type": "info",
            "icon": "🎯",
            "title": "Portfolio has fewer than 3 holdings",
            "sub": "Concentration in 1–2 names dramatically increases volatility. Even adding 2–3 uncorrelated positions can reduce overall portfolio risk significantly."
        })

    if not items:
        items.append({
            "type": "success",
            "icon": "✅",
            "title": "Portfolio looks well-structured",
            "sub": "No major red flags detected. Continue monitoring key positions and macro conditions."
        })

    return items


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _error_card(ticker, qty, cost_basis):
    return {
        "ticker": ticker,
        "headline": "Analysis temporarily unavailable.",
        "bullets": [],
        "sentiment": "Neutral",
        "impact": "Low",
        "key_drivers": [],
        "position_insight": "LLM error. Check server logs.",
        "action_signal": "Monitor",
        "qty": qty,
        "cost_basis": cost_basis,
    }


def mock_fallback(holdings: list[dict]) -> list[dict]:
    mock_data = {
        "AAPL": {
            "headline": "AAPL revenue grows 5% YoY to $119B, iPhone units beat by 2M on China recovery.",
            "bullets": [
                "iPhone revenue up 6% YoY; China unit sales +8% — reversal from prior quarter's -12%.",
                "Services segment hit $26B (record), now 22% of revenue — higher-margin anchor for the multiple.",
                "Risk: EU DMA compliance costs estimated at $1–2B annually; FX headwinds from strong dollar persist.",
            ],
            "sentiment": "Bullish",
            "impact": "Medium",
            "key_drivers": ["China iPhone demand recovery", "Services margin expansion"],
            "position_insight": "At your cost basis, AAPL trades at ~28x forward P/E — premium but justified by Services growth. The China recovery removes the largest bear case. Near-term catalyst: next earnings print in ~6 weeks.",
            "action_signal": "Monitor",
        },
        "NVDA": {
            "headline": "NVDA data center revenue surges 409% YoY to $47.5B; Blackwell ramp ahead of schedule.",
            "bullets": [
                "Data center revenue $47.5B, +409% YoY — hyperscalers (MSFT, GOOG, META) all guided up on AI capex.",
                "Blackwell GPU (B100/B200) shipments accelerating; gross margins guided at 73–74% — above consensus 72%.",
                "Competitor risk: AMD MI300X gaining traction in inference workloads; INTC Gaudi 3 lagging 2yr+ behind.",
            ],
            "sentiment": "Bullish",
            "impact": "High",
            "key_drivers": ["AI infrastructure supercycle", "Blackwell architecture ramp"],
            "position_insight": "NVDA trades at ~35x forward earnings — expensive but supported by a 3-year earnings CAGR estimate of 40%+. Your position benefits from continued hyperscaler capex; key risk is if MSFT/GOOG slow AI infrastructure spending in H2.",
            "action_signal": "Review",
        },
    }
    results = []
    for h in holdings:
        t    = h["ticker"]
        base = mock_data.get(t, {
            "headline": f"No mock data for {t}. Set FEATHERLESS_API_KEY for live analysis.",
            "bullets": ["Configure your API key in the .env file."],
            "sentiment": "Neutral", "impact": "Low",
            "key_drivers": [], "position_insight": "Set FEATHERLESS_API_KEY to get real analysis.",
            "action_signal": "Monitor",
        })
        base["ticker"]     = t
        base["qty"]        = h.get("qty", 0)
        base["cost_basis"] = h.get("cost_basis", 0)
        results.append(base)
    return results


def mock_overall(holdings, analytics):
    tickers = [h["ticker"] for h in holdings]
    return {
        "bluf": f"Your portfolio ({', '.join(tickers)}) is positioned in high-quality growth assets; today's setup is cautiously bullish pending macro catalysts.",
        "body": "NVDA remains the highest-conviction position given the AI infrastructure supercycle showing no signs of demand softening. AAPL's China recovery removes the key bear overhang but Services growth is the real driver to watch.\n\nMarket-wide, rising yields are a technical headwind for growth multiples — watch the 10yr Treasury. Any print above 4.8% tends to trigger rotation from growth to value.\n\nNo major news events today, but CPI report is due this week — a hot print could reprice rate-cut expectations and compress Q4 tech valuations.",
        "portfolio_sentiment": "Bullish",
        "watch_item": "10yr Treasury yield direction and any Fed commentary ahead of this week's CPI release."
    }
