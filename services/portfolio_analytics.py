import yfinance as yf
import numpy as np
from datetime import datetime


# Sector / asset-class mapping fallback
CRYPTO_KEYWORDS = {"BTC", "ETH", "SOL", "ADA", "DOGE", "XRP", "MATIC", "AVAX", "LTC", "BNB"}


def get_portfolio_analytics(holdings: list[dict]) -> dict:
    """
    Pull 1-year daily data for each ticker, compute:
      - Current value, gain/loss per holding
      - Portfolio weight (by market value)
      - Sector / asset-class breakdown
      - Volatility (annualised std-dev of daily returns)
      - Portfolio-level Sharpe estimate (risk-free = 4.5%)
      - Correlation matrix (as list-of-lists for JSON)
      - Diversification score (0-100)
    """
    tickers = [h["ticker"] for h in holdings]
    ticker_info: dict[str, dict] = {}
    price_data: dict = {}   # ticker -> pd.Series (Adj Close)

    # -----------------------------------------------------------------------
    # 1. Fetch data
    # -----------------------------------------------------------------------
    for h in holdings:
        t = h["ticker"]
        qty = h.get("qty", 0)
        cost_basis = h.get("cost_basis", 0)

        is_crypto = t in CRYPTO_KEYWORDS or t.endswith("-USD")
        yf_symbol = f"{t}-USD" if is_crypto and "-USD" not in t else t

        try:
            info_obj = yf.Ticker(yf_symbol)
            hist = info_obj.history(period="1y")
            info = info_obj.info

            if hist.empty:
                current_price = cost_basis  # fallback
            else:
                current_price = float(hist["Close"].iloc[-1])
                price_data[t] = hist["Close"].copy()

            market_value = qty * current_price if qty else current_price
            gain_loss = (current_price - cost_basis) * qty if qty and cost_basis else 0
            gain_pct = ((current_price - cost_basis) / cost_basis * 100) if cost_basis else 0

            sector = info.get("sector") or ("Crypto" if is_crypto else "Unknown")
            asset_class = "Crypto" if is_crypto else "Equity"

            ticker_info[t] = {
                "ticker": t,
                "current_price": round(current_price, 2),
                "market_value": round(market_value, 2),
                "gain_loss": round(gain_loss, 2),
                "gain_pct": round(gain_pct, 2),
                "sector": sector,
                "asset_class": asset_class,
                "qty": qty,
                "cost_basis": cost_basis,
            }
        except Exception as e:
            print(f"Error fetching {t}: {e}")
            ticker_info[t] = {
                "ticker": t,
                "current_price": cost_basis,
                "market_value": 0,
                "gain_loss": 0,
                "gain_pct": 0,
                "sector": "Unknown",
                "asset_class": "Unknown",
                "qty": qty,
                "cost_basis": cost_basis,
            }

    # -----------------------------------------------------------------------
    # 2. Portfolio weights
    # -----------------------------------------------------------------------
    total_value = sum(ticker_info[t]["market_value"] for t in tickers)
    for t in tickers:
        mv = ticker_info[t]["market_value"]
        ticker_info[t]["weight_pct"] = round((mv / total_value * 100) if total_value else 0, 2)

    # -----------------------------------------------------------------------
    # 3. Returns & Volatility
    # -----------------------------------------------------------------------
    returns: dict[str, any] = {}
    for t, series in price_data.items():
        daily_ret = series.pct_change().dropna()
        ann_vol = float(daily_ret.std() * np.sqrt(252)) * 100  # as %
        ticker_info[t]["annual_volatility_pct"] = round(ann_vol, 2)
        returns[t] = daily_ret
    
    # Portfolio-level metrics (weight-average returns)
    portfolio_daily = None
    for t, ret_series in returns.items():
        w = ticker_info[t]["weight_pct"] / 100
        if portfolio_daily is None:
            portfolio_daily = ret_series * w
        else:
            # align indices
            portfolio_daily = portfolio_daily.add(ret_series * w, fill_value=0)

    portfolio_sharpe = None
    portfolio_ann_return = None
    portfolio_ann_vol = None
    if portfolio_daily is not None and len(portfolio_daily) > 20:
        rf_daily = 0.045 / 252
        excess = portfolio_daily - rf_daily
        sharpe = (excess.mean() / excess.std()) * np.sqrt(252)
        portfolio_sharpe = round(float(sharpe), 2)
        portfolio_ann_return = round(float(portfolio_daily.mean() * 252 * 100), 2)
        portfolio_ann_vol = round(float(portfolio_daily.std() * np.sqrt(252) * 100), 2)

    # -----------------------------------------------------------------------
    # 4. Correlation matrix
    # -----------------------------------------------------------------------
    import pandas as pd
    corr_matrix = None
    corr_tickers = list(returns.keys())
    if len(corr_tickers) >= 2:
        df = pd.DataFrame({t: returns[t] for t in corr_tickers}).dropna()
        if len(df) > 10:
            corr = df.corr().round(3)
            corr_matrix = {
                "tickers": corr_tickers,
                "matrix": corr.values.tolist(),
            }

    # -----------------------------------------------------------------------
    # 5. Sector / Asset class breakdown
    # -----------------------------------------------------------------------
    sector_weights: dict[str, float] = {}
    asset_weights: dict[str, float] = {}
    for t in tickers:
        info = ticker_info[t]
        sector_weights[info["sector"]] = sector_weights.get(info["sector"], 0) + info["weight_pct"]
        asset_weights[info["asset_class"]] = asset_weights.get(info["asset_class"], 0) + info["weight_pct"]

    # -----------------------------------------------------------------------
    # 6. Diversification score heuristic
    # -----------------------------------------------------------------------
    n = len(tickers)
    unique_sectors = len(sector_weights)
    max_weight = max((ticker_info[t]["weight_pct"] for t in tickers), default=100)
    
    conc_penalty = max(0, max_weight - 25) * 0.8  # penalise >25% single name
    sector_bonus = min(unique_sectors * 8, 50)     # up to 50pts for many sectors
    size_bonus = min(n * 5, 30)                    # up to 30pts for size
    div_score = max(0, min(100, 20 + sector_bonus + size_bonus - conc_penalty))

    # Qualitative label
    if div_score >= 70:
        div_label = "Well Diversified"
    elif div_score >= 45:
        div_label = "Moderately Diversified"
    else:
        div_label = "Concentrated"

    # Flags & warnings
    flags = []
    for sector, pct in sector_weights.items():
        if pct > 50 and sector not in ("Unknown",):
            flags.append(f"High concentration in {sector} ({pct:.0f}%)")
    for t in tickers:
        if ticker_info[t]["weight_pct"] > 40:
            flags.append(f"{t} dominates portfolio at {ticker_info[t]['weight_pct']}%")

    return {
        "total_value": round(total_value, 2),
        "holdings": list(ticker_info.values()),
        "portfolio_metrics": {
            "annual_return_pct": portfolio_ann_return,
            "annual_volatility_pct": portfolio_ann_vol,
            "sharpe_ratio": portfolio_sharpe,
        },
        "diversification": {
            "score": round(div_score),
            "label": div_label,
            "sector_breakdown": sector_weights,
            "asset_class_breakdown": asset_weights,
            "flags": flags,
        },
        "correlation_matrix": corr_matrix,
    }
