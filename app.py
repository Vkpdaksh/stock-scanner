import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import time

st.set_page_config(page_title="Institutional Market Scanner", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    div[data-testid="stMetricValue"] {font-size: 20px;}
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Pro Market Scanner & Terminal")

# -------------------------------------------------------------
# MASTER WATCHLISTS
# -------------------------------------------------------------
INDIAN_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS",
    "KOTAKBANK.NS", "LT.NS", "BHARTIARTL.NS", "ITC.NS", "HINDUNILVR.NS", "TATAMOTORS.NS", "MARUTI.NS",
    "M&M.NS", "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
    "TITAN.NS", "BAJFINANCE.NS", "ADANIENT.NS", "ADANIPORTS.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS",
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
    "GC=F",      # XAUUSD
    "SI=F",      # XAGUSD
    "CL=F",      # Crude Oil
    "HG=F",      # Copper
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

# Top Controls Bar
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    market_choice = st.selectbox(
        "Market Select Karein:",
        ["Forex & Commodities", "Indian Stocks (NSE)", "US Stocks", "Crypto (24x7)"]
    )

with col2:
    only_breakouts = st.checkbox("Sirf Live Breakouts 🔥", value=False)

with col3:
    auto_refresh = st.checkbox("Auto-Refresh (60s) ⏱️", value=True)

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
# ENGINE
# -------------------------------------------------------------
@st.cache_data(ttl=30)
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
            open_p = float(df['Open'].iloc[-1])
            high_25 = float(df['High'].iloc[-25:-1].max())
            vol = float(df['Volume'].iloc[-1])
            avg_vol = float(df['Volume'].iloc[-25:-1].mean()) or 1.0

            rsi_series = ta.momentum.rsi(df['Close'], window=14)
            rsi = round(float(rsi_series.dropna().iloc[-1]), 1) if not rsi_series.dropna().empty else 50.0

            rvol = round(vol / avg_vol, 2) if avg_vol > 0 else 1.0
            
            # Pure Breakout Rule
            is_breakout = (close > high_25) and (close > open_p)

            atr_series = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            atr = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else (close * 0.01)

            sl = round(close - (1.0 * atr), 2 if "=" not in ticker else 4)
            tp = round(close + (1.5 * atr), 2 if "=" not in ticker else 4)

            # Name Mapping
            display_name = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
            tv_symbol = display_name
            if ticker == "GC=F":
                display_name = "XAUUSD (Gold)"
                tv_symbol = "GOLD"
            elif ticker == "SI=F":
                display_name = "XAGUSD (Silver)"
                tv_symbol = "SILVER"
            elif ticker == "CL=F":
                display_name = "CRUDE OIL"
                tv_symbol = "USOIL"

            chart_url = f"https://in.tradingview.com/chart/?symbol={tv_symbol}"

            results.append({
                "Asset": display_name,
                "Signal": "🟢 BUY BREAKOUT" if is_breakout else "⚪ WAITING",
                "LTP": f"{currency_sym}{round(close, 2 if '=' not in ticker else 4)}",
                "Stop Loss": f"{currency_sym}{sl}",
                "Target (1:1.5)": f"{currency_sym}{tp}",
                "RSI (14)": rsi,
                "RVol": rvol,
                "Chart": chart_url,
                "Is_Breakout": is_breakout
            })
        except Exception:
            continue

    return pd.DataFrame(results)

with st.spinner("Market Momentum Scan Ho Raha Hai..."):
    df_results = fetch_and_scan(selected_tickers)

if not df_results.empty:
    if only_breakouts:
        df_results = df_results[df_results["Is_Breakout"] == True]

    # Clean UI Columns
    display_df = df_results.drop(columns=["Is_Breakout"])

    st.dataframe(
        display_df,
        column_config={
            "Chart": st.column_config.LinkColumn("TradingView", display_text="Open Chart ↗")
        },
        use_container_width=True,
        height=620
    )
else:
    st.info("Market data fetch ho raha hai, kripya thoda wait karein.")

# Auto-Refresh Logic
if auto_refresh:
    time.sleep(60)
    st.rerun()
