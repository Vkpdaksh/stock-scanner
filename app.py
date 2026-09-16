import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(page_title="Market Scanner", layout="centered")

st.markdown("""
<style>
    /* Mobile screen spacing optimization */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

st.subheader("⚡ Live Market Scanner")

market_choice = st.selectbox(
    "Market Chuniye:",
    ["Indian Stocks (NSE)", "US Stocks (NASDAQ/NYSE)", "Forex (Currencies)", "Crypto"]
)

if market_choice == "Indian Stocks (NSE)":
    currency = "₹"
    WATCHLIST = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "BHARTIARTL.NS", "ITC.NS", "LT.NS", "TATAMOTORS.NS", "SBIN.NS",
        "ADANIENT.NS", "SUNPHARMA.NS", "BAJFINANCE.NS", "TITAN.NS", "TATASTEEL.NS"
    ]
elif market_choice == "US Stocks (NASDAQ/NYSE)":
    currency = "$"
    WATCHLIST = [
        "AAPL", "NVDA", "TSLA", "MSFT", "AMZN",
        "META", "GOOGL", "AMD", "NFLX", "INTC"
    ]
elif market_choice == "Forex (Currencies)":
    currency = ""
    WATCHLIST = [
        "USDINR=X", "EURUSD=X", "GBPUSD=X", "USDJPY=X", 
        "AUDUSD=X", "USDCAD=X", "USDCHF=X", "EURINR=X", 
        "GBPINR=X", "JPYINR=X"
    ]
else:
    currency = "$"
    WATCHLIST = [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "DOGE-USD"
    ]

def fetch_analysis(ticker):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty or len(df) < 20:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        rsi_series = ta.momentum.rsi(close, window=14)
        atr_series = ta.volatility.average_true_range(high, low, close, window=14)
        vol_sma_series = volume.rolling(window=20).mean()

        ltp = float(close.iloc[-1])
        curr_rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0
        curr_atr = float(atr_series.iloc[-1]) if not atr_series.empty else (ltp * 0.015)
        curr_vol = float(volume.iloc[-1]) if not volume.empty else 0
        avg_vol = float(vol_sma_series.iloc[-1]) if not vol_sma_series.empty else 1

        recent_high = float(high.iloc[-21:-1].max())

        is_breakout = ltp > recent_high
        is_volume_spike = curr_vol > (1.5 * avg_vol) if avg_vol > 0 else False

        signal = "WATCH"
        if is_breakout and is_volume_spike:
            signal = "🚀 STRONG"
        elif is_breakout:
            signal = "🔥 BREAKOUT"
        elif is_volume_spike:
            signal = "⚡ VOL SURGE"

        dec = 4 if "=X" in ticker else 2
        buy_level = round(ltp, dec)
        stop_loss = round(ltp - curr_atr, dec)
        target = round(ltp + (2 * curr_atr), dec)

        clean_symbol = ticker.replace(".NS", "").replace("=X", "")

        return {
            "Asset": clean_symbol,
            f"Buy ({currency})" if currency else "Buy": buy_level,
            f"SL ({currency})" if currency else "SL": stop_loss,
            f"TP ({currency})" if currency else "TP": target,
            "RSI": round(curr_rsi, 1),
            "Signal": signal
        }
    except Exception:
        return None

col1, col2 = st.columns([1, 1])
with col1:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()
with col2:
    filter_active = st.checkbox("Sirf Alerts/Breakouts", value=False)

with st.spinner("Market scan ho raha hai..."):
    results = []
    for sym in WATCHLIST:
        data = fetch_analysis(sym)
        if data:
            results.append(data)

if results:
    df_res = pd.DataFrame(results)
    if filter_active:
        df_res = df_res[df_res["Signal"] != "WATCH"]

    if not df_res.empty:
        # Aapke paper sketch ke format me clean table
        st.dataframe(
            df_res,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Abhi kisi asset me naya signal/breakout trigger nahi hua hai.")
else:
    st.warning("Data fetch nahi ho saka. Kripya refresh karein.")
