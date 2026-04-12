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
                       profile: dict, macro_news: list[dict] = None,
                       movements: dict = None) -> list[dict]:
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
        movements = movements or {}
        price_change = movements.get(ticker, 0.0)
        movement_ctx = f"Price Movement (last 24-48h): {price_change}%"

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
- {movement_ctx}
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
        weight = h.get("weight_pct", 0)
        if weight > 40:
            items.append({
                "type": "danger",
                "category": "Risk Management",
                "icon": "",
                "title": f"Critical Concentration: {h['ticker']}",
                "technical_desc": f"The position in {h['ticker']} has reached a terminal concentration level of {weight:.1f}% NAV. This creates a dangerous skew where idiosyncratic volatility overpowers systemic trends. In an adverse event specific to {h['ticker']}, the portfolio is mathematically predisposed to catastrophic drawdown regardless of overall market health.",
                "sub": f"Extreme NAV skew ({weight:.1f}%) requires immediate rebalancing.",
                "execution_example": f"Liquidate sufficient lots to reduce the effective weight to under 20%. Re-allocate the proceeds into uncorrelated index hedges or cash equivalents to restore the portfolio's risk-parity baseline.",
                "beginner_tip": "Having too much of one stock is risky. If it drops, your whole portfolio hurts. Diversifying helps spread that risk."
            })
        elif weight > 25:
            items.append({
                "type": "warning",
                "category": "Risk Management",
                "icon": "",
                "title": f"Elevated Position Sizing: {h['ticker']}",
                "technical_desc": f"With a {weight:.1f}% allocation, {h['ticker']} is approaching the threshold where its beta dominates the portfolio's directional movement. Sustained exposure at this level requires high conviction in secular outperformance; otherwise, the risk-adjusted return profile begins to degrade due to lack of asset orthogonality.",
                "sub": f"Monitoring {h['ticker']} for potential 'whale' risk at {weight:.1f}% weight.",
                "execution_example": f"Implement a scaling-out strategy: trim 15-20% of the current position to capture realized gains, or utilize out-of-the-money protective puts to cap downside tail-risk without triggering a taxable event.",
                "beginner_tip": "This stock is becoming a large part of your portfolio. It's wise to keep an eye on it to make sure it doesn't get too big."
            })

    # 2. Sector concentration
    sectors = div.get("sector_breakdown", {})
    for sector, pct in sectors.items():
        if sector not in ("Unknown", "Crypto") and pct > 55:
            items.append({
                "type": "warning",
                "category": "Structural Risk",
                "icon": "",
                "title": f"Structural Sector Saturation: {sector}",
                "technical_desc": f"The portfolio currently exhibits a high degree of thematic clustering in {sector} ({pct:.0f}%). This lack of sector-level diversification exposes the capital base to 'black swan' regulatory changes, interest rate sensitivities, or supply chain shocks unique to the {sector} vertical.",
                "sub": f"High thematic clustering in {sector} creates structural vulnerability.",
                "execution_example": f"Execute a capital rotation out of the most overextended {sector} names and into 'orthogonally' positioned sectors like Healthcare (XLV) or Consumer Staples (XLP) to achieve a more robust diversification factor.",
                "beginner_tip": "You have a lot of stocks in one industry. If that industry has a bad day, most of your stocks will go down together."
            })

    # 3. Sharpe ratio
    sharpe = m.get("sharpe_ratio")
    if sharpe is not None:
        if sharpe < 0:
            items.append({
                "type": "danger",
                "category": "Performance Efficiency",
                "icon": "",
                "title": "Sub-Optimal Risk-Adjusted Returns",
                "technical_desc": f"The portfolio is currently operating with a negative Sharpe Ratio ({sharpe}). This indicates that the realized returns are not only failing to beat the risk-free rate, but that the investor is paying for high volatility without any associated alpha. The portfolio is essentially 'bleeding' without compensated risk.",
                "sub": f"Inefficient risk-capture detected (Sharpe {sharpe}).",
                "execution_example": "Perform a rigorous audit of high-volatility speculative positions. Rotate equity into defensive anchors or short-duration treasuries to stabilize the equity curve until market conditions or internal thesis aligns.",
                "beginner_tip": "Your portfolio is currently very 'bumpy' for the amount of profit you're making. You might be taking too much risk for the return."
            })
        elif sharpe < 0.5:
            items.append({
                "type": "warning",
                "category": "Performance Efficiency",
                "icon": "",
                "title": "Low Portfolio Efficiency Index",
                "technical_desc": f"A Sharpe of {sharpe} suggests that the yield-per-unit-of-risk is significantly lower than institutional benchmarks (typically 0.7 - 1.2). The portfolio is likely over-leveraged in momentum-driven assets with high standard deviations that lack corresponding directional strength.",
                "sub": f"Yield-per-unit-risk ({sharpe}) lags historical market averages.",
                "execution_example": "Optimize the 'Efficient Frontier' of the portfolio by reducing the weight of high-variance assets and increasing exposure to low-correlation instruments like dividends or fixed-income ETFs.",
                "beginner_tip": "Efficiency is key. You want to make the most money possible while keeping the ups-and-downs manageable."
            })
        elif sharpe > 1.5:
            items.append({
                "type": "success",
                "category": "Performance Alpha",
                "icon": "",
                "title": "Superior Risk-Adjusted Allocation",
                "technical_desc": f"The portfolio is exhibiting a superior Sharpe Ratio of {sharpe}. This level of performance indicates a disciplined selection of assets that deliver high returns with exceptionally controlled volatility—outperforming standard systematic returns on a risk-adjusted basis.",
                "sub": f"Exceptional risk-adjusted performance (Sharpe {sharpe}).",
                "execution_example": "The current allocation is highly efficient. Avoid reflexive rebalancing that takes capital away from winning themes; instead, increase the stop-loss thresholds to lock in gains without exiting the secular trend.",
                "beginner_tip": "Great job! This means your investments are working well together to give you smooth, consistent returns."
            })

    # 4. Missing sector exposure (expansion)
    covered_sectors = set(s.lower() for s in sectors.keys())
    if not any("energy" in s or "utilities" in s for s in covered_sectors):
        items.append({
            "type": "info",
            "category": "Diversification",
            "icon": "",
            "title": "Expansion: Secular Inflation Hedge",
            "technical_desc": "The portfolio lacks exposure to the 'Energy and Utilities' vertical, which serves as a critical macro-hedge during inflationary cycles. These assets often generate free cash flow that is uncorrelated with growth-oriented consumer tech, providing a 'hard asset' floor to the NAV.",
            "sub": "Lacking core inflation/commodity hedges in current mix.",
            "execution_example": "Allocate 7-10% into XLE (Energy SPDR) or specialized midstream companies to capture elevated energy commodity pricing without excessive direct oil-price delta.",
            "beginner_tip": "Energy and Utility companies often stay steady or go up when other stocks go down, helping balance your portfolio."
        })
    if not any("health" in s for s in covered_sectors):
        items.append({
            "type": "info",
            "category": "Diversification",
            "icon": "",
            "title": "Expansion: Defensive Biotech & Pharma Anchor",
            "technical_desc": "Zero healthcare exposure creates a vulnerability to 'risk-off' market environments. Healthcare as a sector is characterized by inelastic demand and strong balance sheets, acting as a defensive 'flywheel' that provides liquidity and stability when cyclical sectors rotate lower.",
            "sub": "Zero exposure to defensive healthcare buffer.",
            "execution_example": "Build a tiered entry into XLV (Healthcare ETF) or deep-value biosciences. Aim for a 5-8% weighting to lower the aggregate portfolio beta (sensitivity) to market-wide volatility.",
            "beginner_tip": "Healthcare is considered 'defensive' because people need it regardless of how the economy is doing, making it a safe choice."
        })

    # 5. Underwater positions
    for h in hs:
        gain_pct = h.get("gain_pct", 0)
        if gain_pct < -20 and h.get("qty", 0):
            items.append({
                "type": "warning",
                "category": "Tactical Review",
                "icon": "",
                "title": f"Strategic Stop-Loss Review: {h['ticker']}",
                "technical_desc": f"The position in {h['ticker']} is currently in a deep technical drawdown of {abs(gain_pct):.1f}%. If the original fundamental narrative for this asset has changed, the capital is currently being wasted in a 'dead money' position that incurs significant opportunity cost.",
                "sub": f"{h['ticker']} drawdown ({abs(gain_pct):.1f}%) warrants immediate thesis validation.",
                "execution_example": "Evaluate the asset's distance from its 200-day moving average. If it remains below resistance, execute a tax-loss harvesting sell to offset realized capital gains elsewhere in the portfolio.",
                "beginner_tip": "This stock has lost quite a bit of value. It's a good time to decide if you still believe in it or if it's better to move on."
            })

    # 6. Diversification Minimums
    if len(holdings) < 3:
        items.append({
            "type": "info",
            "category": "Foundational Setup",
            "icon": "",
            "title": "Expansion: Structural Diversification Floor",
            "technical_desc": "With fewer than 3 holdings, the portfolio is effectively 'binary'—reliant on single-event outcomes. Modern Portfolio Theory suggests that the most efficient risk reduction occurs when moving from 1 to 15 holdings, drastically reducing the impact of any single asset's failure.",
            "sub": "Concentration risk is at an absolute maximum with <3 assets.",
            "execution_example": "Immediately prioritize capital expansion into uncorrelated asset classes. Aim to reach a baseline of 5-8 foundational holdings across Tech, Healthcare, Resources, and Fixed-Income vectors.",
            "beginner_tip": "Starting with at least 3-5 different stocks is better than just 1 or 2. It's the simplest way to protect yourself from big losses."
        })

    if not items:
        items.append({
            "type": "success",
            "category": "Institutional Protocol",
            "icon": "",
            "title": "Institutional-Grade Allocation",
            "technical_desc": "The portfolio currently meets the 'Heimdall Standard' for risk-parity and sector distribution. Momentum, volatility, and diversification factors are harmonized to capture systematic growth while mitigating tail-risk events.",
            "sub": "Current metrics align with best-in-class allocation standards.",
            "execution_example": "No tactical interventions required. Sustain current positioning and monitor technical support levels to ensure the portfolio remains on the efficient frontier.",
            "beginner_tip": "Everything looks good! Your portfolio is well-balanced and safe for now."
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
