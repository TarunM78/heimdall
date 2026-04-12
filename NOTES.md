# Heimdall Newstracker - Technical Notes

Heimdall is an AI-powered personalized portfolio intelligence tool. It processes user stock holdings, fetches relevant news, quantifies portfolio metrics, and synthesizes a morning brief utilizing an LLM.

## 1. System Components & Architecture

The application is built using a **FastAPI backend** (Python) and a **Vanilla JS/HTML/CSS frontend**, ensuring minimal external dependency overhead.

### 1.1 Backend Core (`main.py`)
- **Web Framework**: Utilizes FastAPI.
- **State Management**: Uses in-memory dictionaries and lists (`holdings_db`, `profile_db`) instead of an external database.
- **Endpoints**:
  - `GET /api/portfolio`, `POST /api/portfolio`, `POST /api/portfolio/csv` for portfolio management.
  - `GET /api/analytics` maps to portfolio analysis tools.
  - `GET /api/brief` & `GET /api/overall_brief` map to LLM insights.
  - `GET /api/actions` for actionable portfolio suggestions.
  - `GET /api/profile`, `POST /api/profile` for risk parameter management.
- **Static Mounting**: Mounts the `static/` directory to serve the frontend on `/`.

### 1.2 Data Services (`services/`)
- **`news_service.py`**:
  - Connects to **NewsAPI** (`newsapi.org`).
  - Fetches news from the last 7 days querying either broad macroeconomic terms (inflation, Fed rates) or company-specific queries (e.g., "AAPL stock OR AAPL earnings").
- **`portfolio_analytics.py`**:
  - Uses `yfinance`, `numpy`, and `pandas`.
  - Calculates comprehensive quantitative portfolio markers: cumulative returns, beta (vs. SPY benchmark), annualized volatility, historical Value at Risk (VaR), Sharpe Ratio, and diversification score.
  - Also calculates stress-testing against market conditions.
- **`llm_analysis.py`**:
  - Connects to the **Featherless AI** using OpenAI's Python client SDK running the `NousResearch/Meta-Llama-3-8B-Instruct` model.
  - Responsible for generating the natural language daily brief and per-ticker analysis cards.
  - Enforces strict JSON return formats from the LLM.
  - **`generate_action_items()`**: Rule-based (non-LLM) suggestions to notify users of high-concentration risks, sector imbalance, or low risk-adjusted returns (Sharpe < 0.5).

### 1.3 Frontend (`static/`)
- **`index.html`**: A lightweight SPA interface separated into tabs (Brief, Analytics, Actions, Portfolio) with modals for user profiling.
- **`app.js`**: Core client-side vanilla JavaScript manipulating DOM states and connecting UI interactions to FastAPI rest endpoints.
- **`styles.css`**: Provides a modern, dark-themed responsive UI mimicking a Bloomberg-terminal-esque aesthetic.

## 2. Technical Execution Flow

1. **Initialization**: Uvicorn spins up the FastAPI server, exposing RESTful endpoints and serving static files.
2. **User Data**: The user uploads their portfolio via CSV or manual entry.
3. **Trigger Analysis**: When asking for the morning brief, the backend first uses `news_service.py` to get news -> evaluates data using `portfolio_analytics.py` -> feeds both into `llm_analysis.py` to synthesize LLM outputs using custom prompts.
4. **Display**: The DOM in `app.js` updates with newly rendered cards, metrics, and actionable items.
