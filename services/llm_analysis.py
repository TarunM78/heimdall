import os
import json
from openai import OpenAI


def analyze_news_batch(holdings: list[dict], news_batch: list[dict], profile: dict) -> list[dict]:
    api_key = os.getenv("FEATHERLESS_API_KEY")
    if not api_key or api_key == "replace_with_your_featherless_key":
        print("Warning: FEATHERLESS_API_KEY not set. Using mock data.")
        return mock_fallback(holdings)

    base_url = os.getenv("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
    model_name = os.getenv("FEATHERLESS_MODEL", "NousResearch/Meta-Llama-3-8B-Instruct")

    client = OpenAI(api_key=api_key, base_url=base_url)

    # Group news by ticker
    news_by_ticker: dict[str, list[str]] = {}
    for item in news_batch:
        t = item["ticker"]
        news_by_ticker.setdefault(t, [])
        title = item.get("title") or ""
        desc = item.get("description") or ""
        news_by_ticker[t].append(f"- {title}. {desc}")

    # Build user context string
    risk = profile.get("risk_tolerance", "Moderate")
    horizon = profile.get("investment_horizon", "Long-term")
    user_name = profile.get("name") or "the investor"

    results = []

    for holding in holdings:
        ticker = holding["ticker"]
        qty = holding.get("qty", 0)
        cost_basis = holding.get("cost_basis", 0)
        articles = news_by_ticker.get(ticker, [])

        if not articles:
            continue

        articles_text = "\n".join(articles[:5])  # cap at 5 articles

        position_context = ""
        if qty and cost_basis:
            position_context = f"They hold {qty} units at an average cost of ${cost_basis:.2f}."
        elif qty:
            position_context = f"They hold {qty} units."

        prompt = f"""You are a professional financial analyst AI named Heimdall.

User profile: {user_name}, risk tolerance: {risk}, investment horizon: {horizon}.
{position_context}

Here are recent news articles about {ticker}:
{articles_text}

Respond ONLY with a valid raw JSON object (no markdown, no ```json blocks). Use EXACTLY this structure:
{{
  "ticker": "{ticker}",
  "headline": "One sharp sentence capturing the most important development.",
  "bullets": ["bullet 1", "bullet 2", "bullet 3"],
  "sentiment": "Bullish" or "Bearish" or "Neutral",
  "impact": "High" or "Medium" or "Low",
  "key_drivers": ["driver1", "driver2"],
  "position_insight": "1-2 sentences explaining what this means specifically for this user's position and risk profile.",
  "action_signal": "Monitor" or "Review" or "Act"
}}"""

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a financial analyst AI. Output ONLY raw JSON, no markdown, no explanation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=450,
            )

            raw = response.choices[0].message.content.strip()
            # Strip any markdown blocks the model may have added
            raw = raw.strip("`").strip()
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()

            # Find first { ... } block
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

            parsed = json.loads(raw)
            # Ensure ticker is set correctly
            parsed["ticker"] = ticker
            # Include position data for frontend display
            parsed["qty"] = qty
            parsed["cost_basis"] = cost_basis
            results.append(parsed)

        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            results.append({
                "ticker": ticker,
                "headline": "Analysis unavailable.",
                "bullets": [],
                "sentiment": "Neutral",
                "impact": "Low",
                "key_drivers": [],
                "position_insight": "Could not connect to analysis engine.",
                "action_signal": "Monitor",
                "qty": qty,
                "cost_basis": cost_basis,
            })

    return results


def mock_fallback(holdings: list[dict]) -> list[dict]:
    mock_data = {
        "AAPL": {
            "headline": "iPhone demand stabilizes in China amid trade concerns.",
            "bullets": [
                "iPhone units sold in China rose 3% YoY despite macro headwinds.",
                "Apple supplier TSMC guided higher on advanced node demand.",
                "EU digital markets act compliance costs remain a near-term headwind.",
            ],
            "sentiment": "Bullish",
            "impact": "Medium",
            "key_drivers": ["China demand recovery", "Supply chain normalization"],
            "position_insight": "Your AAPL position benefits from stabilizing China revenue, though regulatory costs keep near-term upside capped.",
            "action_signal": "Monitor",
        },
        "NVDA": {
            "headline": "AI chip demand continues to overwhelm NVDA supply capacity.",
            "bullets": [
                "NVDA H100 allocation wait times extend to 6+ months.",
                "Microsoft and Google both increased infrastructure capex guidance.",
                "AMD MI300X gains traction but remains 18 months behind on software ecosystem.",
            ],
            "sentiment": "Bullish",
            "impact": "High",
            "key_drivers": ["AI infrastructure buildout", "Hyperscaler capex acceleration"],
            "position_insight": "Strong structural tailwinds support your NVDA position. High impact warrants a close watch on Blackwell ramp for a possible price catalyst.",
            "action_signal": "Review",
        },
    }

    results = []
    for h in holdings:
        t = h["ticker"]
        base = mock_data.get(t, {
            "headline": f"No mock data available for {t}.",
            "bullets": ["News data unavailable in mock mode."],
            "sentiment": "Neutral",
            "impact": "Low",
            "key_drivers": [],
            "position_insight": "Set FEATHERLESS_API_KEY for real analysis.",
            "action_signal": "Monitor",
        })
        base["ticker"] = t
        base["qty"] = h.get("qty", 0)
        base["cost_basis"] = h.get("cost_basis", 0)
        results.append(base)
    return results
