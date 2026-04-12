import asyncio
from services.yfinance_service import get_ticker_news
from services.llm_analysis import _get_client, _parse_json
import os

async def test_msft():
    news = await get_ticker_news("MSFT")
    
    print(f"News length for MSFT: {len(news)}")
    if news:
        print("First article:", news[0])

    articles_text = "\\n".join([f"• {n.get('title','')}." for n in news[:6]])
    
    prompt = f"""You are Heimdall, a sharp institutional-grade financial analyst.
USER CONTEXT:
- Ticker: MSFT
RECENT COMPANY-SPECIFIC NEWS:
{articles_text}
TASK: Produce a precise, company-specific assessment. Be specific.

Respond ONLY with a valid raw JSON object. No markdown. No preamble:
{{
  "ticker": "MSFT",
  "headline": "One punchy sentence",
  "bullets": ["Point 1", "Point 2"],
  "sentiment": "Bullish",
  "impact": "High",
  "key_drivers": ["one", "two"],
  "position_insight": "Position impact text.",
  "action_signal": "Monitor"
}}"""
    client, model = _get_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a financial analyst. Output ONLY raw JSON, no markdown."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=600,
        )
        content = response.choices[0].message.content
        print("--- RAW LLM OUTPUT ---")
        print(content)
        print("--- END RAW ---")
        parsed = _parse_json(content)
        print("PARSED TYPE:", type(parsed))
    except Exception as e:
        print("Error:", e)

asyncio.run(test_msft())
