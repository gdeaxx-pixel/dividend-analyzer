import pandas_datareader.data as web
import datetime

def check_stooq():
    start = datetime.datetime(2024, 1, 1)
    end = datetime.datetime.now()
    
    print("Checking MSTY on Stooq...")
    try:
        # Stooq codes often need .US suffix for user stocks
        df = web.DataReader('MSTY.US', 'stooq', start, end)
        if not df.empty:
            print("Success! Found MSTY on Stooq.")
            print(df.head())
        else:
            print("Dataframe empty.")
    except Exception as e:
        print(f"Failed to fetch from Stooq: {e}")

    print("\nChecking MSTY without suffix...")
    try:
        df = web.DataReader('MSTY', 'stooq', start, end)
        if not df.empty:
            print("Success! Found MSTY on Stooq (no suffix).")
            print(df.head())
    except Exception as e:
        print(f"Failed to fetch from Stooq (no suffix): {e}")

if __name__ == "__main__":
    check_stooq()
