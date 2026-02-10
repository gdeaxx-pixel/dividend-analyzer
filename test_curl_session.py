from curl_cffi import requests as crequests
import yfinance as yf
import pandas as pd

def test_curl_session():
    print("Testing explicit curl_cffi session injection...")
    
    # Create a curl_cffi session
    # mimicking a real browser (impersonate="chrome")
    session = crequests.Session(impersonate="chrome")
    
    ticker = "MSTY"
    start_date = "2024-01-01"
    
    print("\n1. Testing yf.Ticker().history() with session...")
    try:
        t = yf.Ticker(ticker, session=session)
        data = t.history(start=start_date, auto_adjust=False, actions=True)
        print(f"Success! Data shape: {data.shape}")
        if not data.empty:
            print(data.head())
    except Exception as e:
        print(f"Failed Ticker history: {e}")

    print("\n2. Testing yf.download() with session...")
    try:
        data = yf.download(ticker, start=start_date, progress=False, auto_adjust=False, actions=True, session=session)
        print(f"Success! Data shape: {data.shape}")
    except Exception as e:
        print(f"Failed download: {e}")

if __name__ == "__main__":
    test_curl_session()
