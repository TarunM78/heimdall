import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime


# Sector / asset-class mapping fallback
CRYPTO_KEYWORDS = {"BTC", "ETH", "SOL", "ADA", "DOGE", "XRP", "MATIC", "AVAX", "LTC", "BNB"}


def _strip_tz(series):
    """Remove timezone info from a pandas Series index."""
    if hasattr(series.index, 'tz') and series.index.tz is not None:
        series = series.copy()
        series.index = series.index.tz_localize(None)
    return series


def get_portfolio_analytics(holdings: list[dict]) -> dict:
    """
    Pull 1-year daily data for each ticker, compute:
      - Current value, gain/loss, weight
      - Sector / asset-class breakdown
      - Per-holding: volatility, beta, 52w high/low, valuation metrics
      - Portfolio: Sharpe, VaR, benchmark comparison vs SPY
      - Stress test scenarios
      - Correlation matrix
      - Diversification score
    """
    tickers = [h["ticker"] for h in holdings]
    ticker_info: dict[str, dict] = {}
    price_data: dict = {}

    # -----------------------------------------------------------------------
    # 1. Fetch SPY benchmark first
    # -----------------------------------------------------------------------
    spy_series = None
    spy_returns = None
    try:
        spy_hist = yf.Ticker("SPY").history(period="1y")
        if not spy_hist.empty:
            spy_series = _strip_tz(spy_hist["Close"].copy())
            spy_returns = spy_series.pct_change().dropna()
    except Exception as e:
        print(f"Error fetching SPY benchmark: {e}")

    # -----------------------------------------------------------------------
    # 2. Fetch per-holding data
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
                current_price = cost_basis or 0
                sparkline = []
                week_52_high = week_52_low = week_52_pct = annual_return_pct = None
            else:
                hist_close = _strip_tz(hist["Close"].copy())
                current_price = float(hist_close.iloc[-1])
                price_data[t] = hist_close
                sparkline = [round(float(v), 2) for v in hist_close.tail(30).values]
                week_52_high = round(float(hist_close.max()), 2)
                week_52_low  = round(float(hist_close.min()), 2)
                _range = week_52_high - week_52_low
                week_52_pct = round((current_price - week_52_low) / _range * 100, 1) if _range > 0 else 50.0
                annual_return_pct = round((current_price / float(hist_close.iloc[0]) - 1) * 100, 2) if float(hist_close.iloc[0]) > 0 else 0

            # ---- Upcoming Earnings Calendar ----
            upcoming_earnings = None
            try:
                cal = info_obj.calendar
                if cal and isinstance(cal, dict) and "Earnings Date" in cal:
                    dates = cal["Earnings Date"]
                    if dates and len(dates) > 0:
                        upcoming_earnings = dates[0].strftime("%Y-%m-%d")
            except Exception:
                pass

            market_value = qty * current_price if qty else current_price

            # ---- Sector / asset detection ----
            quote_type = info.get("quoteType", "").upper()
            long_name  = (info.get("longName") or info.get("shortName") or "").lower()
            sector = info.get("sector")
            asset_class = "Equity"

            if is_crypto or quote_type == "CRYPTOCURRENCY":
                asset_class = "Crypto"
                sector = "Crypto"
            elif quote_type == "ETF":
                asset_class = "ETF"
                if any(k in long_name for k in ["bond", "treasury", "fixed income", "debt", "yield"]):
                    sector = "Fixed Income"
                elif any(k in long_name for k in ["s&p 500", "index", "market", "nasdaq", "dow jones", "total stock", "russell"]):
                    sector = "Index / Broad Market"
                elif any(k in long_name for k in ["gold", "silver", "commodity", "oil", "gas"]):
                    sector = "Commodities"
                elif any(k in long_name for k in ["real estate", "reit"]):
                    sector = "Real Estate"
                else:
                    sector = "ETF / Diversified"

            if not sector:
                sector = "Unknown / Other"

            description = info.get("longBusinessSummary") or info.get("description") or ""
            
            gain_loss = (current_price - cost_basis) * qty if qty and cost_basis else 0
            gain_pct  = ((current_price - cost_basis) / cost_basis * 100) if cost_basis else 0

            # ---- Valuation metrics ----
            fwd_pe     = info.get("forwardPE")
            ttm_pe     = info.get("trailingPE")
            pe_ratio   = fwd_pe or ttm_pe
            pe_type    = "fwd" if fwd_pe else ("ttm" if ttm_pe else None)
            p_to_sales = info.get("priceToSalesTrailing12Months")
            p_to_book  = info.get("priceToBook")
            div_yield  = info.get("dividendYield")

            ticker_info[t] = {
                "ticker":             t,
                "current_price":      round(current_price, 2),
                "market_value":       round(market_value, 2),
                "gain_loss":          round(gain_loss, 2),
                "gain_pct":           round(gain_pct, 2),
                "sector":             sector,
                "asset_class":        asset_class,
                "qty":                qty,
                "cost_basis":         cost_basis,
                "sparkline":          sparkline,
                "week_52_high":       week_52_high,
                "week_52_low":        week_52_low,
                "week_52_pct":        week_52_pct,
                "pe_ratio":           round(pe_ratio, 1) if pe_ratio else None,
                "pe_type":            pe_type,
                "price_to_sales":     round(p_to_sales, 2) if p_to_sales else None,
                "price_to_book":      round(p_to_book, 2) if p_to_book else None,
                "dividend_yield_pct": round(div_yield * 100, 2) if div_yield else None,
                "annual_return_pct":  annual_return_pct,
                "upcoming_earnings":  upcoming_earnings,
                "description":        description,
            }
        except Exception as e:
            print(f"Error fetching {t}: {e}")
            ticker_info[t] = {
                "ticker": t, "current_price": cost_basis or 0,
                "market_value": 0, "gain_loss": 0, "gain_pct": 0,
                "sector": "Unknown", "asset_class": "Unknown",
                "qty": qty, "cost_basis": cost_basis, "sparkline": [],
                "week_52_high": None, "week_52_low": None, "week_52_pct": None,
                "pe_ratio": None, "pe_type": None,
                "price_to_sales": None, "price_to_book": None, "dividend_yield_pct": None,
                "annual_return_pct": None, "upcoming_earnings": None,
                "description": "",
            }

    # -----------------------------------------------------------------------
    # 3. Portfolio weights
    # -----------------------------------------------------------------------
    total_value = sum(ticker_info[t]["market_value"] for t in tickers)
    for t in tickers:
        mv = ticker_info[t]["market_value"]
        ticker_info[t]["weight_pct"] = round((mv / total_value * 100) if total_value else 0, 2)

    # -----------------------------------------------------------------------
    # 4. Returns, Volatility, Beta
    # -----------------------------------------------------------------------
    returns: dict = {}
    for t, series in price_data.items():
        daily_ret = series.pct_change().dropna()
        ann_vol   = float(daily_ret.std() * np.sqrt(252)) * 100
        ticker_info[t]["annual_volatility_pct"] = round(ann_vol, 2)
        returns[t] = daily_ret

        # Beta vs SPY
        if spy_returns is not None:
            aligned = pd.DataFrame({"stock": daily_ret, "spy": spy_returns}).dropna()
            if len(aligned) > 20:
                cov_val = aligned["stock"].cov(aligned["spy"])
                var_val = aligned["spy"].var()
                ticker_info[t]["beta"] = round(cov_val / var_val, 2) if var_val != 0 else None
            else:
                ticker_info[t]["beta"] = None
        else:
            ticker_info[t]["beta"] = None

    # -----------------------------------------------------------------------
    # 5. Portfolio-level time series & metrics
    # -----------------------------------------------------------------------
    portfolio_daily = None
    for t, ret_series in returns.items():
        w = ticker_info[t]["weight_pct"] / 100
        if portfolio_daily is None:
            portfolio_daily = ret_series * w
        else:
            portfolio_daily = portfolio_daily.add(ret_series * w, fill_value=0)

    portfolio_sharpe = portfolio_ann_return = portfolio_ann_vol = None
    var_1d_95 = var_1m_95 = None

    if portfolio_daily is not None and len(portfolio_daily) > 20:
        rf_daily = 0.045 / 252
        excess   = portfolio_daily - rf_daily
        sharpe   = (excess.mean() / excess.std()) * np.sqrt(252)
        portfolio_sharpe     = round(float(sharpe), 2)
        portfolio_ann_return = round(float(portfolio_daily.mean() * 252 * 100), 2)
        portfolio_ann_vol    = round(float(portfolio_daily.std() * np.sqrt(252) * 100), 2)
        # Historical VaR at 95% confidence (5th worst percentile daily loss)
        var_1d_95 = round(float(np.percentile(portfolio_daily.values, 5)) * 100, 2)
        var_1m_95 = round(var_1d_95 * np.sqrt(21), 2)

    # -----------------------------------------------------------------------
    # 6. Benchmark comparison — portfolio vs SPY cumulative 1yr
    # -----------------------------------------------------------------------
    benchmark_comparison = None
    if portfolio_daily is not None and spy_returns is not None and len(portfolio_daily) > 20:
        port_cumret = (1 + portfolio_daily).cumprod() - 1
        spy_cumret  = (1 + spy_returns).cumprod() - 1

        aligned_bench = pd.DataFrame({"portfolio": port_cumret, "spy": spy_cumret}).dropna()
        if len(aligned_bench) > 20:
            try:
                aligned_bench = aligned_bench.resample("W").last().dropna()
            except Exception:
                pass  # use daily if resample fails

            dates      = [str(d)[:10] for d in aligned_bench.index]
            port_series = [round(float(v) * 100, 2) for v in aligned_bench["portfolio"]]
            spy_series  = [round(float(v) * 100, 2) for v in aligned_bench["spy"]]

            if port_series and spy_series:
                benchmark_comparison = {
                    "dates": dates,
                    "portfolio_cumulative": port_series,
                    "spy_cumulative": spy_series,
                    "portfolio_total_return_pct": port_series[-1],
                    "spy_total_return_pct": spy_series[-1],
                    "alpha": round(port_series[-1] - spy_series[-1], 2),
                }

    # -----------------------------------------------------------------------
    # 7. Stress test — market downturn scenarios using portfolio beta
    # -----------------------------------------------------------------------
    valid_betas = [(ticker_info[t].get("beta") or 1.0, ticker_info[t]["weight_pct"] / 100) for t in tickers]
    portfolio_beta = round(sum(b * w for b, w in valid_betas), 2)

    stress_scenarios = []
    for drop_pct in [-5, -10, -20, -30]:
        est_pct   = round(drop_pct * portfolio_beta, 1)
        est_dollar = round(total_value * est_pct / 100, 2)
        stress_scenarios.append({
            "label":               f"S&P {drop_pct}%",
            "market_drop_pct":     drop_pct,
            "est_portfolio_pct":   est_pct,
            "est_dollar_impact":   est_dollar,
        })

    # -----------------------------------------------------------------------
    # 8. Correlation matrix
    # -----------------------------------------------------------------------
    corr_matrix = None
    corr_tickers = list(returns.keys())
    if len(corr_tickers) >= 2:
        df = pd.DataFrame({t: returns[t] for t in corr_tickers}).dropna()
        if len(df) > 10:
            corr = df.corr().round(3)
            corr_matrix = {"tickers": corr_tickers, "matrix": corr.values.tolist()}

    # -----------------------------------------------------------------------
    # 9. Sector / asset class breakdown
    # -----------------------------------------------------------------------
    sector_weights: dict[str, float] = {}
    asset_weights:  dict[str, float] = {}
    for t in tickers:
        d = ticker_info[t]
        sector_weights[d["sector"]]     = sector_weights.get(d["sector"], 0)     + d["weight_pct"]
        asset_weights[d["asset_class"]] = asset_weights.get(d["asset_class"], 0) + d["weight_pct"]

    # -----------------------------------------------------------------------
    # 10. Diversification score
    # -----------------------------------------------------------------------
    n              = len(tickers)
    unique_sectors = len(sector_weights)
    max_weight     = max((ticker_info[t]["weight_pct"] for t in tickers), default=100)
    conc_penalty   = max(0, max_weight - 25) * 0.8
    sector_bonus   = min(unique_sectors * 8, 50)
    size_bonus     = min(n * 5, 30)
    div_score      = max(0, min(100, 20 + sector_bonus + size_bonus - conc_penalty))

    if   div_score >= 70: div_label = "Well Diversified"
    elif div_score >= 45: div_label = "Moderately Diversified"
    else:                 div_label = "Concentrated"

    flags = []
    for sector, pct in sector_weights.items():
        if pct > 50 and sector not in ("Unknown",):
            flags.append(f"High concentration in {sector} ({pct:.0f}%)")
    for t in tickers:
        if ticker_info[t]["weight_pct"] > 40:
            flags.append(f"{t} dominates portfolio at {ticker_info[t]['weight_pct']}%")

    return {
        "total_value": round(total_value, 2),
        "holdings":    list(ticker_info.values()),
        "portfolio_metrics": {
            "annual_return_pct":     portfolio_ann_return,
            "annual_volatility_pct": portfolio_ann_vol,
            "sharpe_ratio":          portfolio_sharpe,
            "portfolio_beta":        portfolio_beta,
            "var_1d_95":             var_1d_95,
            "var_1m_95":             var_1m_95,
        },
        "diversification": {
            "score":             round(div_score),
            "label":             div_label,
            "sector_breakdown":  sector_weights,
            "asset_class_breakdown": asset_weights,
            "flags":             flags,
        },
        "correlation_matrix":   corr_matrix,
        "benchmark_comparison": benchmark_comparison,
        "stress_scenarios":     stress_scenarios,
        "portfolio_beta":       portfolio_beta,
    }
