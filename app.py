import streamlit as st
import pandas as pd
import yfinance as yf
import ta

st.set_page_config(
    page_title="Pro Market Scanner",
    page_icon="⚡",
    layout="wide"
)

# Mobile padding and header spacing fix
st.markdown("""
<style>
    .block-container {
        padding-top: 4.5rem !important;
        padding-bottom: 2rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
    }
    header[data-testid="stHeader"] {
        z-index: 1;
    }
    h2 {
        margin-top: 0.5rem !important;
        font-size: 1.6rem !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚡ Pro Market Scanner")

MARKET_OPTIONS = {
    "Indian Stocks (NSE)": {
        "symbols": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", 
                    "BHARTIARTL.NS", "ITC.NS", "LT.NS", "TATAMOTORS.NS", "SBIN.NS", "TITAN.NS"],
        "currency": "₹"
    },
    "US Stocks": {
        "symbols": ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META"],
        "currency": "$"
    },
    "Crypto": {
        "symbols": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"],
        "currency": "$"
    },
    "Forex & Commodities": {
        "symbols": ["GC=F", "CL=F", "EURUSD=X", "GBPUSD=X", "USDINR=X"],
        "currency": ""
    }
}

selected_market = st.selectbox("Market Select Karein:", list(MARKET_OPTIONS.keys()))
only_breakouts = st.checkbox("Sirf Breakouts 🔥", value=False)

market_info = MARKET_OPTIONS[selected_market]
symbols = market_info["symbols"]
curr = market_info["currency"]

@st.cache_data(ttl=60)
def fetch_market_data(ticker_list):
    records = []
    for sym in ticker_list:
        try:
            df = yf.download(sym, period="6mo", interval="1d", progress=False)
            if df.empty or len(df) < 30:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] for col in df.columns]

            close = df['Close']
            high = df['High']
            low = df['Low']
            volume = df['Volume']

            ema_50 = ta.trend.ema_indicator(close, window=50)
            atr = ta.volatility.average_true_range(high, low, close, window=14)
            vol_sma20 = volume.rolling(window=20).mean()
            rsi = ta.momentum.rsi(close, window=14)

            ltp = float(close.iloc[-1])
            c_atr = float(atr.iloc[-1]) if not atr.empty else (ltp * 0.02)
            c_ema50 = float(ema_50.iloc[-1]) if not ema_50.empty else ltp
            curr_vol = float(volume.iloc[-1]) if not volume.empty else 0
            avg_vol = float(vol_sma20.iloc[-1]) if not vol_sma20.empty else 1
            c_rsi = float(rsi.iloc[-1]) if not rsi.empty else 50.0

            recent_high = float(high.iloc[-21:-1].max()) if len(high) >= 22 else float(high.max())
            is_breakout = (ltp > recent_high) and (ltp >= c_ema50)
            rvol = curr_vol / avg_vol if avg_vol > 0 else 1.0

            if is_breakout and rvol >= 1.6:
                signal = "🚀 STRONG BREAKOUT"
            elif is_breakout:
                signal = "🔥 BREAKOUT"
            else:
                signal = "WATCH"

            sl = round(ltp - (1.2 * c_atr), 2)
            tp = round(ltp + (2.0 * c_atr), 2)
            clean_sym = sym.replace(".NS", "").replace("-USD", "").replace("=X", "").replace("=F", "")

            records.append({
                "Asset": clean_sym,
                "Buy": round(ltp, 2),
                "SL": sl,
                "TP": tp,
                "RSI": round(c_rsi, 1),
                "RVol": f"{round(rvol, 1)}x",
                "Signal": signal
            })
        except Exception:
            continue

    return pd.DataFrame(records)

with st.spinner("Market data fetch ho raha hai..."):
    df_data = fetch_market_data(symbols)

if not df_data.empty:
    if only_breakouts:
        df_data = df_data[df_data["Signal"] != "WATCH"]

    if df_data.empty:
        st.info("Filhal is market mein koi breakout setup active nahi hai.")
    else:
        if curr:
            df_data["Buy"] = df_data["Buy"].apply(lambda x: f"{curr}{x}")
            df_data["SL"] = df_data["SL"].apply(lambda x: f"{curr}{x}")
            df_data["TP"] = df_data["TP"].apply(lambda x: f"{curr}{x}")

        # Streamlit Native Interactive Table (Zero rendering crashes on mobile)
        st.dataframe(df_data, use_container_width=True, hide_index=True)
else:
    st.warning("Data load nahi hua. Kripya 1 minute baad dobara refresh karein.")
