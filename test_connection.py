
import requests
import yfinance as yf
import sys

def test_connectivity():
    print("Testing general internet connectivity (google.com)...")
    try:
        response = requests.get("https://www.google.com", timeout=5)
        print(f"Google status code: {response.status_code}")
    except Exception as e:
        print(f"Google connection failed: {e}")

    print("\nTesting Yahoo Finance connectivity (yfinance)...")
    try:
        ticker = yf.Ticker("TSLY")
        hist = ticker.history(period="1d")
        if not hist.empty:
            print("yfinance fetch success!")
            print(hist)
        else:
            print("yfinance fetch returned empty dataframe.")
    except Exception as e:
        print(f"yfinance fetch failed: {e}")

if __name__ == "__main__":
    test_connectivity()
