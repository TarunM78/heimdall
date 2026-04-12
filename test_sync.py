import os
from dotenv import load_dotenv
# Load environment variables FIRST
load_dotenv(override=True)

from services.snaptrade_service import snaptrade_service

def test_sync():
    user_id = os.getenv("SNAPTRADE_TEST_USER_ID")
    user_secret = os.getenv("SNAPTRADE_TEST_USER_SECRET")
    
    if not user_id or not user_secret:
        print("❌ Test credentials missing in .env")
        return

    print(f"🧪 Testing sync for user: {user_id}")
    try:
        holdings = snaptrade_service.fetch_holdings(user_id, user_secret)
        print(f"✅ Sync successful! Found {len(holdings)} holdings:")
        for h in holdings:
            print(f"   - {h['ticker']}: {h['qty']} (Avg Cost: ${h['cost_basis']:.2f})")
    except Exception as e:
        print(f"❌ Sync failed with error: {e}")

if __name__ == "__main__":
    test_sync()
