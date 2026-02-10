from curl_cffi import requests as crequests
import pandas as pd
import io

def scrape_history_html(ticker):
    print(f"Scraping HTML for {ticker}...")
    url = f"https://finance.yahoo.com/quote/{ticker}/history?p={ticker}"
    
    session = crequests.Session(impersonate="chrome")
    try:
        response = session.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            # Simple check for data table
            if "Historical Data" in response.text:
                print("Found 'Historical Data' in HTML.")
                
                # Try regex parsing for table rows if read_html fails
                import re
                print("Attempting regex parsing...")
                # Find all table rows
                rows = re.findall(r'<tr.*?>(.*?)</tr>', response.text, re.DOTALL)
                print(f"Found {len(rows)} rows.")
                
                data = []
                for row in rows:
                    cols = re.findall(r'<td.*?>(.*?)</td>', row, re.DOTALL)
                    # Clean tags from cols
                    cols = [re.sub(r'<.*?>', '', c).strip() for c in cols]
                    if len(cols) >= 5: # Valid price row usually has Date, Open, High, Low, Close, Adj Close, Volume
                        data.append(cols)
                
                print(f"Extracted {len(data)} data rows.")
                if len(data) > 0:
                    print("First row:", data[0])
                    # Create DataFrame
                    df = pd.DataFrame(data)
                    # Try to identify columns based on length (usually 7 for history)
                    if len(df.columns) == 7:
                        df.columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
                    print(df.head())
                    return df
            else:
                print("Did not find 'Historical Data' text.")
                
                # Check for "Too Many Requests" text in HTML body
                if "Too Many Requests" in response.text or "429" in response.text:
                    print("DETECTED RATE LIMIT IN HTML BODY.")
        else:
            print(f"Failed to fetch page. Status: {response.status_code}")
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    scrape_history_html("MSTY")
