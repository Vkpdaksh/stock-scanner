import streamlit as st
import yfinance as yf
import pandas as pd
import ta

st.set_page_config(page_title="Global Momentum Scanner", layout="centered")

# Custom CSS for Mobile friendly styling
st.markdown("""
<style>
    .metric-box {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 8px;
        border-left: 4px solid #1E88E5;
    }
    .badge-breakout {
        background-color: #ff4b4b;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .badge-watch {
        background-color: #6c757d;
        color: white;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("⚡ Market Scanner")
st.caption("Live Breakouts & 1:2 Risk-Reward Engine")

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

        is_breakout = ltp > recent_high
        is_volume_spike = curr_vol > (1.5 * avg_vol) if avg_vol > 0 else False

        signal = "WATCH"
        if is_breakout and is_volume_spike:
            signal = "🚀 STRONG BREAKOUT"
        elif is_breakout:
            signal = "🔥 PRICE BREAKOUT"
        elif is_volume_spike:
            signal = "⚡ VOLUME SHOCKER"

        dec = 4 if "=X" in ticker else 2
        buy_level = round(ltp, dec)
        stop_loss = round(ltp - curr_atr, dec)
        risk = round(curr_atr, dec)
        target = round(ltp + (2 * curr_atr), dec)

        clean_symbol = ticker.replace(".NS", "").replace("=X", "")

        return {
            "Asset": clean_symbol,
            "LTP": buy_level,
            "Change %": round(change_pct, 2),
            "Signal": signal,
            "RSI": round(curr_rsi, 1),
            "Buy Level": buy_level,
            "Stop Loss": stop_loss,
            "Target (1:2)": target,
            "Risk": risk,
            "Currency": currency
        }
    except Exception:
        return None

col_a, col_b = st.columns([1, 1])
with col_a:
    if st.button("🔄 Refresh Rates", use_container_width=True):
        st.rerun()
with col_b:
    filter_choice = st.radio("Filter:", ["Sirf Breakouts 🔥", "Sabhi Assets 📋"], horizontal=True)

with st.spinner("Market scan ho raha hai..."):
    results = []
    for sym in WATCHLIST:
        d = fetch_analysis(sym)
        if d:
            results.append(d)

if results:
    df_res = pd.DataFrame(results)
    
    if "Sirf Breakouts" in filter_choice:
        display_data = [r for r in results if r["Signal"] != "WATCH"]
        if not display_data:
            st.info("Abhi kisi asset mein high surge ya breakout nahi hai. Sabhi dekhne ke liye 'Sabhi Assets' chunein.")
    else:
        display_data = results

    # Mobile Cards Layout (Upar se Neeche Rows)
    for item in display_data:
        cur = item["Currency"]
        with st.container(border=True):
            # Top row: Name, Signal Badge, Change %
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown(f"### *{item['Asset']}*")
                if item['Signal'] != "WATCH":
                    st.markdown(f"<span class='badge-breakout'>{item['Signal']}</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span class='badge-watch'>{item['Signal']}</span>", unsafe_allow_html=True)
            with c2:
                chg = item['Change %']
                color = "green" if chg >= 0 else "red"
                sign = "+" if chg >= 0 else ""
                st.markdown(f"<h3 style='text-align:right; color:{color}; margin:0;'>{sign}{chg}%</h3>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align:right; margin:0; color:gray;'>RSI: <b>{item['RSI']}</b></p>", unsafe_allow_html=True)

            st.divider()

            # Mobile Row: Buy, Stop Loss, Target in clean horizontal columns inside card
            m1, m2, m3 = st.columns(3)
            m1.metric("Buy Level", f"{cur}{item['Buy Level']}")
            m2.metric("Stop Loss", f"{cur}{item['Stop Loss']}")
            m3.metric("Target (1:2)", f"{cur}{item['Target (1:2)']}")
else:
    st.warning("Data load nahi hua. Kripya 'Refresh' dabayein.")
