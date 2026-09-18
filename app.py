import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import time

st.set_page_config(page_title="Institutional Breakout Terminal", page_icon="⚡", layout="wide")

# Custom Dark Terminal Styling
st.markdown("""
    <style>
    .metric-box {
        background-color: #1e222d;
        padding: 12px;
        border-radius: 8px;
        border-left: 4px solid #00c805;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Institutional Breakout Terminal")

# -------------------------------------------------------------
# WATCHLIST REGISTRY
# -------------------------------------------------------------
WATCHLISTS = {
    "Forex & Commodities": [
        "GC=F", "SI=F", "CL=F", "HG=F", "INR=X", "EURUSD=X", 
        "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"
    ],
    "Indian High-Beta Momentum": [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
        "LT.NS", "BHARTIARTL.NS", "TATAMOTORS.NS", "TITAN.NS", "SUZLON.NS", "IREDA.NS",
        "RVNL.NS", "IRFC.NS", "MAZDOCK.NS", "HAL.NS", "BEL.NS", "BSE.NS", "CDSL.NS",
        "ZOMATO.NS", "TRENT.NS", "DIXON.NS", "POLYCAB.NS", "TATAPOWER.NS"
    ],
    "US Tech Giants": [
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", 
        "AMD", "NFLX", "PLTR", "AVGO", "SMCI", "COIN", "MSTR"
    ],
    "Crypto (24x7)": [
        "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "DOGE-USD", "SUI-USD"
    ]
}

# -------------------------------------------------------------
# TOP BAR CONTROLS
# -------------------------------------------------------------
col1, col2, col3, col4 = st.columns([2, 1.2, 1, 1])

with col1:
    market_choice = st.selectbox("Market Select Karein:", list(WATCHLISTS.keys()))

with col2:
    min_rvol = st.slider("Minimum RVol (Volume Spike):", min_value=1.0, max_value=3.0, value=1.4, step=0.1)

with col3:
    only_breakouts = st.checkbox("Sirf Breakouts 🔥", value=False)

with col4:
    auto_refresh = st.checkbox("Auto-Sync (60s) ⏱️", value=True)

selected_tickers = WATCHLISTS[market_choice]
currency_sym = "₹" if "Indian" in market_choice else ("$" if market_choice in ["US Tech Giants", "Crypto (24x7)"] else "")

# -------------------------------------------------------------
# ADVANCED SCANNING LOGIC
# -------------------------------------------------------------
@st.cache_data(ttl=30)
def fetch_and_scan(tickers, rvol_threshold):
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

            rvol = round(vol / avg_vol, 2) if avg_vol > 0 else 1.0
            
            # Indicator Calculations
            rsi_series = ta.momentum.rsi(df['Close'], window=14)
            rsi = round(float(rsi_series.dropna().iloc[-1]), 1) if not rsi_series.dropna().empty else 50.0

            atr_series = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            atr = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else (close * 0.01)

            # Breakout Conditions
            is_breakout = (close > high_25) and (close > open_p) and (rvol >= rvol_threshold)

            sl = round(close - (1.0 * atr), 2 if "=" not in ticker else 4)
            tp1 = round(close + (1.5 * atr), 2 if "=" not in ticker else 4)
            risk_unit = max(round(close - sl, 4), 0.0001)
            suggested_qty = max(1, int(1000 / risk_unit)) if currency_sym == "₹" else max(1, int(50 / risk_unit))

            # Display Formatting
            name = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
            tv_sym = name
            if ticker == "GC=F":
                name, tv_sym = "XAUUSD (Gold)", "GOLD"
            elif ticker == "SI=F":
                name, tv_sym = "XAGUSD (Silver)", "SILVER"
            elif ticker == "CL=F":
                name, tv_sym = "CRUDE OIL", "USOIL"

            results.append({
                "Priority": 0 if is_breakout else 1,
                "Asset": name,
                "Signal": "🟢 STRONG BREAKOUT" if is_breakout else "⚪ CONSOLIDATING",
                "LTP": f"{currency_sym}{round(close, 2 if '=' not in ticker else 4)}",
                "Stop-Loss": f"{currency_sym}{sl}",
                "Target (1:1.5)": f"{currency_sym}{tp1}",
                "RVol": f"{rvol}x 🔥" if rvol >= 2.0 else f"{rvol}x",
                "RSI": rsi,
                "Size (~Risk Cap)": f"{suggested_qty} units",
                "Chart": f"https://in.tradingview.com/chart/?symbol={tv_sym}",
                "Is_Breakout": is_breakout
            })
        except Exception:
            continue

    df_out = pd.DataFrame(results)
    if not df_out.empty:
        # Breakout signals ko table me sabse upar sort karein
        df_out = df_out.sort_values(by=["Priority", "Asset"]).drop(columns=["Priority"])
    return df_out

with st.spinner("Market Depth & Momentum Scan Ho Raha Hai..."):
    df_results = fetch_and_scan(selected_tickers, min_rvol)

if not df_results.empty:
    if only_breakouts:
        df_results = df_results[df_results["Is_Breakout"] == True]

    # Quick Summary Metric Cards
    active_breakouts = int(df_results["Is_Breakout"].sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Monitored Assets", len(df_results))
    c2.metric("Active Breakouts", active_breakouts, delta="Actionable" if active_breakouts > 0 else "Neutral")
    c3.metric("RVol Filter Level", f"{min_rvol}x")

    st.dataframe(
        df_results.drop(columns=["Is_Breakout"]),
        column_config={
            "Chart": st.column_config.LinkColumn("Chart", display_text="TradingView ↗")
        },
        use_container_width=True,
        height=580
    )
else:
    st.info("Market data fetch ho raha hai ya market closed hai. Kripya refresh karein.")

if auto_refresh:
    time.sleep(60)
    st.rerun()
