import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(page_title="Global Market Scanner", layout="wide", initial_sidebar_state="collapsed")

st.title("⚡ Global Momentum Scanner & SL/TP Engine")
st.caption("Live Breakouts, Volume Surges & 1:2 Risk-Reward Levels")

# Market Selection Dropdown
market_choice = st.selectbox(
    "Market Chunein:",
    ["Indian Stocks (NSE)", "US Stocks (NASDAQ/NYSE)", "Crypto (USD)"]
)

# Market ke hisab se watchlists aur currency
if market_choice == "Indian Stocks (NSE)":
    WATCHLIST = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "BHARTIARTL.NS", "ITC.NS", "LT.NS", "TATAMOTORS.NS", "SBIN.NS",
        "ADANIENT.NS", "SUNPHARMA.NS", "BAJFINANCE.NS", "TITAN.NS", "TATASTEEL.NS"
    ]
    currency = "₹"
elif market_choice == "US Stocks (NASDAQ/NYSE)":
    WATCHLIST = [
        "AAPL", "NVDA", "TSLA", "MSFT", "AMZN",
        "META", "GOOGL", "AMD", "NFLX", "INTC"
    ]
    currency = "$"
else:
    WATCHLIST = [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "DOGE-USD"
    ]
    currency = "$"

if st.button("🔄 Refresh Data"):
    st.rerun()

results = []

with st.spinner(f"{market_choice} scan ho raha hai... Kripya 5-10 second wait karein."):
    for ticker in WATCHLIST:
        try:
            df = yf.download(ticker, period="6mo", interval="1d", progress=False)
            if len(df) < 30:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            ltp = float(df['Close'].iloc[-1])
            prev_close = float(df['Close'].iloc[-2])
            high_20d = float(df['High'].iloc[-21:-1].max())
            high_52w = float(df['High'].max())
            curr_vol = float(df['Volume'].iloc[-1])
            avg_vol = float(df['Volume'].iloc[-21:-1].mean())

            df['RSI'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
            df['ATR'] = ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()

            rsi = float(df['RSI'].iloc[-1])
            atr = float(df['ATR'].iloc[-1])

            vol_shock = curr_vol >= (1.5 * avg_vol)
            breakout_20d = ltp >= high_20d
            near_52w = ltp >= (0.98 * high_52w)

            signal = "WATCH"
            if breakout_20d and vol_shock:
                signal = "🔥 STRONG BREAKOUT"
            elif near_52w and rsi > 60:
                signal = "🚀 52W MOMENTUM"
            elif vol_shock:
                signal = "⚡ VOLUME SHOCKER"

            stop_loss = round(ltp - (1.5 * atr), 2)
            risk = round(ltp - stop_loss, 2)
            target = round(ltp + (2.0 * risk), 2)

            clean_name = ticker.replace(".NS", "").replace("-USD", "")

            results.append({
                "Asset": clean_name,
                f"LTP ({currency})": round(ltp, 2),
                "Change %": round(((ltp - prev_close) / prev_close) * 100, 2),
                "Signal": signal,
                "RSI": round(rsi, 1),
                f"Buy Level ({currency})": round(ltp, 2),
                f"Stop Loss ({currency})": stop_loss,
                f"Target (1:2) ({currency})": target,
                f"Risk ({currency})": risk
            })
        except Exception:
            continue

df_result = pd.DataFrame(results)

tab1, tab2 = st.tabs(["🎯 Buzzing & Breakouts", "📊 Full Watchlist"])

with tab1:
    buzzing = df_result[df_result["Signal"] != "WATCH"] if not df_result.empty else pd.DataFrame()
    if not buzzing.empty:
        st.dataframe(buzzing, use_container_width=True)
    else:
        st.info("Filhal koi asset breakout criteria match nahi kar raha hai.")

with tab2:
    if not df_result.empty:
        st.dataframe(df_result, use_container_width=True)
    else:
        st.warning("Data fetch karne mein dikkat aayi. Kripya thodi der baad Refresh karein.")