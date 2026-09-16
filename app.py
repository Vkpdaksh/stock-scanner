import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(page_title="Global Momentum Scanner", layout="wide")

st.title("⚡ Global Momentum Scanner & SL/TP Engine")
st.caption("Live Breakouts, Volume Surges & 1:2 Risk-Reward Levels")

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
    currency = "₹/$"
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
        prev_close = float(close.iloc[-2])
        change_pct = ((ltp - prev_close) / prev_close) * 100

        curr_rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0
        curr_atr = float(atr_series.iloc[-1]) if not atr_series.empty else (ltp * 0.015)
        curr_vol = float(volume.iloc[-1]) if not volume.empty else 0
        avg_vol = float(vol_sma_series.iloc[-1]) if not vol_sma_series.empty else 1

        recent_high = float(high.iloc[-21:-1].max())

        # Signals
        is_breakout = ltp > recent_high
        is_volume_spike = curr_vol > (1.5 * avg_vol) if avg_vol > 0 else False

        signal = "WATCH"
        if is_breakout and is_volume_spike:
            signal = "🚀 STRONG BREAKOUT"
        elif is_breakout:
            signal = "🔥 PRICE BREAKOUT"
        elif is_volume_spike:
            signal = "⚡ VOLUME SHOCKER"

        # Risk-Reward Calculations (1:2 ATR based)
        buy_level = round(ltp, 4 if "=X" in ticker else 2)
        stop_loss = round(ltp - curr_atr, 4 if "=X" in ticker else 2)
        risk = round(curr_atr, 4 if "=X" in ticker else 2)
        target = round(ltp + (2 * curr_atr), 4 if "=X" in ticker else 2)

        clean_symbol = ticker.replace(".NS", "").replace("=X", "")

        return {
            "Asset": clean_symbol,
            f"LTP ({currency})": buy_level,
            "Change %": round(change_pct, 2),
            "Signal": signal,
            "RSI": round(curr_rsi, 1),
            f"Buy Level ({currency})": buy_level,
            f"Stop Loss ({currency})": stop_loss,
            f"Target (1:2) ({currency})": target,
            f"Risk ({currency})": risk
        }
    except Exception:
        return None

if st.button("🔄 Refresh Data"):
    st.rerun()

with st.spinner(f"{market_choice} scan ho raha hai... Kripya 5 second rukhein..."):
    results = []
    for sym in WATCHLIST:
        data = fetch_analysis(sym)
        if data:
            results.append(data)

if results:
    df_res = pd.DataFrame(results)

    tab1, tab2 = st.tabs(["🔥 Buzzing & Breakouts", "📋 Full Watchlist"])

    with tab1:
        buzzing = df_res[df_res["Signal"] != "WATCH"]
        if not buzzing.empty:
            st.dataframe(buzzing, use_container_width=True)
        else:
            st.info("Abhi kisi asset mein high volume surge ya breakout nahi hua hai.")

    with tab2:
        st.dataframe(df_res, use_container_width=True)
else:
    st.warning("Data fetch karne mein dikkat aayi. Kripya thodi der baad Refresh karein.")
