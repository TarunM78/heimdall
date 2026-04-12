import os
import json
from datetime import datetime
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
def analyze_news_batch(holdings: list[dict], news_batch: list[dict],
                       profile: dict, macro_news: list[dict] = None) -> list[dict]:
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key or api_key == "replace_with_your_featherless_key":
        return mock_fallback(holdings)

    client, model = _get_client()
    macro_news = macro_news or []

    # Group news by ticker
    news_by_ticker: dict[str, list[str]] = {}
    for item in news_batch:
        t = item.get("ticker")
        if not t:
            continue
        news_by_ticker.setdefault(t, [])
        title = item.get("title") or ""
        desc  = item.get("description") or ""
        if title:
            news_by_ticker[t].append(f"• {title}. {desc}".strip())

    risk    = profile.get("risk_tolerance", "Moderate")
    horizon = profile.get("investment_horizon", "Long-term")

    # ------------------------------------------------------------------
    # Step 1: Identify cross-cutting shared themes from ALL news
    # (these go in the overall brief; per-ticker cards should NOT repeat)
    # ------------------------------------------------------------------
    all_headlines = [item.get("title", "") for item in news_batch if item.get("title")]
    macro_headlines = [f"[MACRO] {m.get('title','')}" for m in macro_news if m.get("title")]
    shared_themes = _extract_shared_themes(client, model, all_headlines + macro_headlines)

    results = []

    for holding in holdings:
        ticker     = holding["ticker"]
        qty        = holding.get("qty", 0)
        cost_basis = holding.get("cost_basis", 0)
        articles   = news_by_ticker.get(ticker, [])

        if not articles:
            results.append({
                "ticker": ticker,
                "headline": f"No significant news found for {ticker} in the last 7 days.",
                "bullets": ["Market news sources showed no major updates."],
                "sentiment": "Neutral",
                "impact": "Low",
                "key_drivers": ["No current news drivers"],
                "position_insight": f"No new catalysts detected in recent hours. Continue holding according to your original investment thesis for {ticker}.",
                "action_signal": "Monitor",
                "qty": qty,
                "cost_basis": cost_basis
            })
            continue

        articles_text = "\n".join(articles[:6])

        position_ctx = ""
        if qty and cost_basis:
            position_ctx = f"Position: {qty} units at avg cost ${cost_basis:.2f}."
        elif qty:
            position_ctx = f"Position: {qty} units (no cost basis provided)."

        shared_ctx = ""
        if shared_themes:
            shared_ctx = (
                "\nSHARED THEMES (already covered in the portfolio overview — DO NOT repeat these):\n"
                + "\n".join(f"- {t}" for t in shared_themes)
                + "\n\nFocus ONLY on what is SPECIFIC and UNIQUE to this ticker."
            )

        source_filter = (
            "\nSOURCE FILTER: Analyst upgrades/downgrades from investment banks (e.g. Wedbush, Goldman, JPM price targets) "
            "are low-information. Do NOT lead with or over-weight them. "
            "Prioritise in this order: (1) government/regulatory actions, (2) Fed/central bank statements, "
            "(3) earnings/revenue data, (4) product launches or M&A, (5) macro events (CPI, tariffs, geopolitics). "
            "Only mention analyst calls if no higher-priority news exists."
        )

        prompt = f"""You are Heimdall, a sharp institutional-grade financial analyst. Today's date is {datetime.utcnow().strftime('%Y-%m-%d')}. Do not hallucinate upcoming events like earnings if they are not specifically mentioned in the news or if you are not certain of the timeline relative to today's date.

USER CONTEXT:
- Ticker: {ticker}
- {position_ctx}
- Risk tolerance: {risk} | Investment horizon: {horizon}
{source_filter}
{shared_ctx}

RECENT COMPANY-SPECIFIC NEWS:
{articles_text}

TASK: Produce a precise, company-specific assessment. Be specific about:
1. What EXACTLY changed (earnings beats/misses with %, regulatory actions, product specifics, named executives)
2. The MECHANISM of impact on this stock's price or fundamentals
3. What this means for THIS position at this cost basis / horizon

Do NOT cover general AI trends, macro rates, or sector themes that affect all tech stocks equally — those belong in the portfolio overview.
Do NOT echo back or mention the user's risk tolerance or investment horizon — that is already known. Write as if speaking to an informed peer.

Respond ONLY with a valid raw JSON object. No markdown. No preamble:
{{
  "ticker": "{ticker}",
  "headline": "One punchy sentence with a company-specific fact or figure.",
  "bullets": [
    "Company-specific development 1 with concrete numbers",
    "Company-specific development 2",
    "Key company-specific risk or catalyst to watch"
  ],
  "sentiment": "Bullish" or "Bearish" or "Neutral",
  "impact": "High" or "Medium" or "Low",
  "key_drivers": ["specific driver 1", "specific driver 2"],
  "position_insight": "2 sentences. State the impact directly. Name the specific mechanism (e.g. margin compression, multiple expansion, revenue beat). Do not mention the user's risk profile or time horizon.",
  "action_signal": "Monitor" or "Review" or "Act"
}}"""

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Output ONLY raw JSON, no markdown."},
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


def _extract_shared_themes(client, model, headlines: list[str]) -> list[str]:
    """Use LLM to identify broad cross-cutting themes across all news."""
    if not headlines:
        return []
    joined = "\n".join(headlines[:20])
    prompt = f"""From the following news headlines, identify 3-5 broad cross-cutting themes that affect MULTIPLE companies (e.g. 'AI capex spending by hyperscalers', 'US tariff escalation', 'Federal Reserve rate expectations'). Do NOT list company-specific events.

Headlines:
{joined}

Return ONLY a JSON array of short theme strings, e.g. ["AI infrastructure spending", "Fed rate uncertainty"].
Return [] if no clear shared themes exist."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=120,
        )
        raw = resp.choices[0].message.content.strip()
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception as e:
        print(f"Shared theme extraction error: {e}")
    return []



# ---------------------------------------------------------------------------
# Portfolio-wide overall brief
# ---------------------------------------------------------------------------
def generate_overall_brief(holdings: list[dict], news_batch: list[dict],
                            analytics: dict, profile: dict,
                            macro_news: list[dict] = None) -> dict:
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key or api_key == "replace_with_your_featherless_key":
        return mock_overall(holdings, analytics)

    client, model = _get_client()
    macro_news = macro_news or []

    tickers = [h["ticker"] for h in holdings]
    risk    = profile.get("risk_tolerance", "Moderate")
    horizon = profile.get("investment_horizon", "Long-term")
    name    = profile.get("name") or "Investor"

    # Flatten top company-specific news per ticker (deduplicated)
    ticker_lines = []
    seen = set()
    for item in news_batch:
        key = item.get("title", "")[:60]
        if key and key not in seen:
            seen.add(key)
            ticker_lines.append(f"[{item['ticker']}] {item.get('title','')}. {item.get('description','')[:120]}")

    # Macro news context (the part that was missing)
    macro_lines = []
    macro_seen = set()
    for m in macro_news:
        key = m.get("title", "")[:60]
        if key and key not in macro_seen:
            macro_seen.add(key)
            macro_lines.append(f"[MACRO] {m.get('title','')}. {m.get('description','')[:120]}")

    # Analytics context
    port_m  = analytics.get("portfolio_metrics", {})
    div     = analytics.get("diversification", {})
    metrics_ctx = ""
    if port_m.get("sharpe_ratio") is not None:
        metrics_ctx = (
            f"Portfolio Sharpe: {port_m['sharpe_ratio']}, "
            f"Annualised vol: {port_m.get('annual_volatility_pct','?')}%, "
            f"est. annual return: {port_m.get('annual_return_pct','?')}%. "
            f"Diversification: {div.get('label','?')} (score {div.get('score','?')}/100)."
        )

    flags = div.get("flags", [])
    flags_ctx = " | ".join(flags) if flags else "No major concentration warnings."

    news_text  = "\n".join(ticker_lines[:12])
    macro_text = "\n".join(macro_lines[:10])

    prompt = f"""You are Heimdall, writing a comprehensive, insightful morning portfolio brief for {name}. Today's date is {datetime.utcnow().strftime('%Y-%m-%d')}.

PORTFOLIO: {', '.join(tickers)}
RISK PROFILE: {risk} | Horizon: {horizon}
{metrics_ctx}
PORTFOLIO FLAGS: {flags_ctx}

MACROECONOMIC & GEOPOLITICAL NEWS (highest priority — always cover what's relevant):
{macro_text if macro_text else "No significant macro news fetched."}

COMPANY-SPECIFIC NEWS:
{news_text if news_text else "No company news fetched."}

SOURCE PRIORITY RULES:
- Government actions (White House, Treasury, Congress) > Federal Reserve statements > Earnings/revenue data > Geopolitical events > Regulatory actions > Analyst/bank calls
- Sell-side analyst upgrades/downgrades (Wedbush, Goldman, etc.) are low-information bias — only mention if nothing more important exists
- Geopolitical events (wars, sanctions, tariffs) MUST be covered if they affect the portfolio

Write a highly detailed, structured, newsletter-style morning portfolio brief. This should be a substantial read for the user over their morning coffee — DO NOT provide just a few sentences. Dive deep into the nuances.
Each section MUST be comprised of rich, insightful paragraphs (at least 3-4 dense paragraphs per section) drawing directly from the news provided.
Do not use bullet points anywhere. Write like a sharp fund manager's daily written macro memo.
Do NOT mention obvious platitudes like "diversification is important" or restate their risk profile.

Respond ONLY with raw JSON — no markdown, no preamble:
{{
  "bluf": "One punchy sentence: the single most important takeaway for the portfolio today.",
  "macro_environment": "A comprehensive 3-4 paragraph deep dive on the macro and geopolitical backdrop. Discuss specific events (e.g. Iran conflict, Fed stance, inflation prints) and carefully explain their structural mechanisms of impact on markets.",
  "portfolio_impact": "A comprehensive 3-4 paragraph detailed breakdown of how today's macro and company news specifically affects the holdings. Name tickers. Synthesize themes. Use numbers where possible.",
  "key_risk": "One specific, data-driven sentence on the single biggest downside risk appearing in CURRENT news. DO NOT give generic platitudes like 'market shock' or 'volatility'. You MUST name a specific catalyst (e.g., 'escalation in the Iran conflict disrupting the Strait of Hormuz', 'a hotter-than-expected CPI print tomorrow').",
  "opportunity": "One specific sentence on the best opportunity or positive catalyst mentioned in the news. Name the specific ticker or macro event (e.g., 'Alphabet's new TPU v5p chips competing with Nvidia', 'China's PPI return to growth signalling industrial demand').",
  "portfolio_sentiment": "Bullish" or "Bearish" or "Mixed",
  "audio_script": "A short, engaging, highly conversational 3-4 sentence script meant to be spoken out loud. You MUST adopt the persona of 'Alfred' (Batman's dry, aristocratic, hyper-competent and loyal British butler). Greet the user by name with sophisticated deference ('Good morning, [Name]', or similar), state the condition of their portfolio affairs, mention the key catalyst of the day, and close loyally. Write it exactly as it should be spoken.",
  "macro_exposures": [
    {{
      "theme": "Short keyword phrase describing a distinct macro theme in the news (e.g. 'Middle East Conflict', 'Rate Cuts', 'AI Infrastructure')",
      "affected_tickers": ["TICKER1", "TICKER2"],
      "impact_direction": "positive" or "negative" or "neutral"
    }}
  ]
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a financial analyst writing morning briefings. Output ONLY raw JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=1000,
        )
        parsed = _parse_json(response.choices[0].message.content)
        return parsed
    except Exception as e:
        print(f"[FALLBACK] Overall brief LLM error: {e} — returning mock data")
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
    today = datetime.utcnow()
    year  = today.year
    month = today.strftime("%B")
    return {
        "bluf": f"[MOCK DATA — LLM unavailable] Portfolio is cautiously positioned as of {month} {year}; macro headwinds from rate uncertainty and geopolitical risk are the primary factors to watch.",
        "macro_environment": f"NOTE: This is fallback mock data generated on {today.strftime('%Y-%m-%d')} because the live LLM analysis failed. Configure your FEATHERLESS_API_KEY for real-time analysis.",
        "portfolio_impact": f"For a tech-heavy portfolio ({', '.join(tickers)}), elevated rates compress forward P/E multiples and geopolitical risk adds volatility. Check server logs for the LLM error.",
        "key_risk": "LLM analysis unavailable — check FEATHERLESS_API_KEY and server logs.",
        "opportunity": "Resolve LLM connectivity to get live analysis.",
        "portfolio_sentiment": "Mixed",
    }
