import os
from snaptrade_client import SnapTrade
from typing import List, Optional, Any

class SnapTradeService:
    def __init__(self):
        self.api_client = SnapTrade(
            client_id=os.getenv("SNAPTRADE_CLIENT_ID"),
            consumer_key=os.getenv("SNAPTRADE_CONSUMER_KEY")
        )

    def _safe_get(self, obj: Any, key: str, default: Any = None) -> Any:
        """Safely get a value from a dict or an object attribute."""
        if obj is None:
            return default
        try:
            # Try dict-style access
            return obj.get(key, default)
        except (AttributeError, TypeError):
            # Try object-style access
            return getattr(obj, key, default)

    def register_user(self, user_id: str):
        """Register a user with SnapTrade or get their existing secret."""
        try:
            response = self.api_client.authentication.register_user(user_id=user_id)
            return response.body  # Contains userSecret
        except Exception as e:
            print(f"SnapTrade registration error: {e}")
            raise e

    def get_login_url(self, user_id: str, user_secret: str, redirect_uri: str):
        """Generate a connection portal URL."""
        try:
            response = self.api_client.authentication.login_snap_trade_user(
                user_id=user_id,
                user_secret=user_secret
            )
            return response.body.get("redirectURI")
        except Exception as e:
            print(f"SnapTrade login error: {e}")
            raise e

    def fetch_holdings(self, user_id: str, user_secret: str) -> List[dict]:
        """Fetch all holdings for all accounts for the user."""
        try:
            print(f"Fetching holdings for user: {user_id}")
            # 1. Get accounts
            accounts_res = self.api_client.account_information.list_user_accounts(
                user_id=user_id,
                user_secret=user_secret
            )
            accounts = accounts_res.body
            
            seen_tickers = {}

            if not isinstance(accounts, list):
                print(f"Unexpected accounts response: {type(accounts)}")
                return []

            # 2. Get holdings for each account
            for acc in accounts:
                acc_id = self._safe_get(acc, "id")
                if not acc_id:
                    print("Skipping account with no ID")
                    continue
                
                print(f"Fetching holdings for account: {acc_id}")
                try:
                    # get_user_holdings returns positions, balances, etc.
                    holdings_res = self.api_client.account_information.get_user_holdings(
                        account_id=str(acc_id), # Ensure string
                        user_id=user_id,
                        user_secret=user_secret
                    )
                    data = holdings_res.body
                    
                    # Handle different response formats for positions
                    positions = []
                    if isinstance(data, list):
                        positions = data
                    else:
                        positions = self._safe_get(data, "positions", [])

                    for p in positions:
                        # Robust ticker extraction
                        symbol_info = self._safe_get(p, "symbol")
                        ticker = None
                        
                        # Symbol info can be a string, a dict, or an object
                        if isinstance(symbol_info, str):
                            ticker = symbol_info
                        else:
                            # Try 'symbol' key inside symbol_info
                            ticker = self._safe_get(symbol_info, "symbol")
                            # If ticker is STILL a dict (nested), try one more level or stringify
                            if isinstance(ticker, dict):
                                ticker = self._safe_get(ticker, "symbol")
                        
                        if not ticker or not isinstance(ticker, str):
                            print(f"Could not extract ticker string from: {symbol_info}")
                            continue

                        ticker = ticker.upper()
                        qty = float(self._safe_get(p, "units", 0) or 0)
                        # price or average_purchase_price
                        cost = float(self._safe_get(p, "average_purchase_price", 0) or 0)
                        
                        if ticker in seen_tickers:
                            old_qty = seen_tickers[ticker]["qty"]
                            old_cost = seen_tickers[ticker]["cost_basis"]
                            new_qty = old_qty + qty
                            if new_qty > 0:
                                avg_cost = ((old_qty * old_cost) + (qty * cost)) / new_qty
                                seen_tickers[ticker]["qty"] = new_qty
                                seen_tickers[ticker]["cost_basis"] = avg_cost
                        else:
                            seen_tickers[ticker] = {"ticker": ticker, "qty": qty, "cost_basis": cost}
                except Exception as acc_e:
                    print(f"Error fetching holdings for account {acc_id}: {acc_e}")
                    continue
            
            return list(seen_tickers.values())
        except Exception as e:
            print(f"SnapTrade fetch holdings root error: {e}")
            raise e

snaptrade_service = SnapTradeService()
