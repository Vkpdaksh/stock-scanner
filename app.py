import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(page_title="Pro Market Scanner", page_icon="⚡", layout="wide")

st.title("⚡ Pro Market Scanner")

# -------------------------------------------------------------
# COMPLETE WATCHLISTS
# -------------------------------------------------------------
INDIAN_STOCKS = [
    # Bluechips & Heavyweights
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS",
    "KOTAKBANK.NS", "LT.NS", "BHARTIARTL.NS", "ITC.NS", "HINDUNILVR.NS", "TATAMOTORS.NS", "MARUTI.NS",
    "M&M.NS", "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
    "TITAN.NS", "BAJFINANCE.NS", "ADANIENT.NS", "ADANIPORTS.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS",
    # Momentum Midcaps, Defence, Railway, Energy
    "SUZLON.NS", "IREDA.NS", "RVNL.NS", "IRFC.NS", "IRCON.NS", "RAILTEL.NS", "MAZDOCK.NS", "COCHINSHIP.NS",
    "HAL.NS", "BEL.NS", "BDL.NS", "BHEL.NS", "HUDCO.NS", "NBCC.NS", "SAIL.NS", "NMDC.NS", "NATIONALUM.NS",
    "BSE.NS", "CDSL.NS", "ANGELONE.NS", "MCX.NS", "TATATECH.NS", "TRENT.NS", "ZOMATO.NS", "JIOFIN.NS",
    "DIXON.NS", "POLYCAB.NS", "KEI.NS", "KALYANKJIL.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "PERSISTENT.NS",
    "COFORGE.NS", "DLF.NS", "LODHA.NS", "AUROPHARMA.NS", "LUPIN.NS", "EXIDEIND.NS", "ASHOKLEY.NS"
]

US_STOCKS = [
    "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "AMD", "NFLX", "PLTR",
    "AVGO", "SMCI", "ARM", "QCOM", "INTC", "MU", "PANW", "CRWD", "COIN", "MSTR"
]

FOREX_COMMODITIES = [
    # Gold & Silver (Spot + Futures)
    "XAUUSD=X",  # Gold Spot
    "XAGUSD=X",  # Silver Spot
    "GC=F",      # Gold Comex Futures
    "SI=F",      # Silver Comex Futures
    "CL=F",      # Crude Oil
    "HG=F",      # Copper
    # 8 Major Global Currencies
    "INR=X",     # USD/INR
    "EURUSD=X",  # EUR/USD
    "GBPUSD=X",  # GBP/USD
    "USDJPY=X",  # USD/JPY
    "AUDUSD=X",  # AUD/USD
    "USDCAD=X",  # USD/CAD
    "USDCHF=X",  # USD/CHF
    "NZDUSD=X"   # NZD/USD
]

CRYPTO = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "SUI-USD"
]

# Market Selection
market_choice = st.selectbox(
    "Market Select Karein:",
    ["Indian Stocks (NSE)", "US Stocks", "Forex & Commodities", "Crypto (24x7)"]
)

only_breakouts = st.checkbox("Sirf Breakouts 🔥")

if market_choice == "Indian Stocks (NSE)":
    selected_tickers = INDIAN_STOCKS
    currency_sym = "₹"
elif market_choice == "US Stocks":
    selected_tickers = US_STOCKS
    currency_sym = "$"
elif market_choice == "Forex & Commodities":
    selected_tickers = FOREX_COMMODITIES
    currency_sym = ""
else:
    selected_tickers = CRYPTO
    currency_sym = "$"

# -------------------------------------------------------------
# SCANNER LOGIC
# -------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_and_scan(tickers):
    results = []
    data = yf.download(tickers, period="5d", interval="15m", group_by='ticker', progress=False)
    
    for ticker in tickers:
        try:
            df = data[ticker] if len(tickers) > 1 else data
            df = df.dropna()
            if len(df) < 25:
                continue

            close = float(df['Close'].iloc[-1])
            high_25 = float(df['High'].iloc[-25:-1].max())
            vol = float(df['Volume'].iloc[-1])
            avg_vol = float(df['Volume'].iloc[-25:-1].mean()) or 1.0

            # RSI Calculation
            rsi_series = ta.momentum.rsi(df['Close'], window=14)
            rsi = round(float(rsi_series.dropna().iloc[-1]), 1) if not rsi_series.dropna().empty else 50.0

            rvol = round(vol / avg_vol, 2) if avg_vol > 0 else 1.0
            is_breakout = close > high_25

            # ATR for Target / SL
            atr_series = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            atr = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else (close * 0.01)

            sl = round(close - (1.0 * atr), 2 if "=" not in ticker else 4)
            tp = round(close + (1.5 * atr), 2 if "=" not in ticker else 4)

            display_name = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
            if ticker == "XAUUSD=X":
                display_name = "GOLD Spot (XAUUSD)"
            elif ticker == "XAGUSD=X":
                display_name = "SILVER Spot (XAGUSD)"

            results.append({
                "Asset": display_name,
                "Buy": f"{currency_sym}{round(close, 2 if '=' not in ticker else 4)}",
                "SL": f"{currency_sym}{sl}",
                "TP": f"{currency_sym}{tp}",
                "RSI": rsi,
                "RVol": rvol,
                "Breakout": is_breakout
            })
        except Exception:
            continue

    return pd.DataFrame(results)

with st.spinner("Market Data Scan Ho Raha Hai..."):
    df_results = fetch_and_scan(selected_tickers)

if not df_results.empty:
    if only_breakouts:
        df_results = df_results[df_results["Breakout"] == True]
    
    st.dataframe(df_results.drop(columns=["Breakout"]), use_container_width=True, height=600)
else:
    st.info("Data load ho raha hai, kripya refresh karein.")
