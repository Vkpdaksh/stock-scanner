import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import time

st.set_page_config(page_title="Institutional Breakout & Option Terminal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    div[data-testid="stMetricValue"] {font-size: 20px;}
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Pro Market Scanner & Index Option Terminal")

# -------------------------------------------------------------
# WATCHLIST REGISTRY
# -------------------------------------------------------------
WATCHLISTS = {
    "⚡ Index Options (Nifty & Bank Nifty)": ["^NSEI", "^NSEBANK", "NIFTY_FIN_SERVICE.NS"],
    "Major Indices (Global)": ["^IXIC", "^GSPC", "^DJI", "^CNXIT", "^CNXAUTO", "^CNXMETAL"],
    "Forex & Commodities": ["GC=F", "SI=F", "CL=F", "HG=F", "INR=X", "EURUSD=X", "GBPUSD=X", "USDJPY=X"],
    "Indian Stocks (NSE)": [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
        "TATAMOTORS.NS", "TITAN.NS", "SUZLON.NS", "IREDA.NS", "RVNL.NS", "HAL.NS", "BEL.NS", "ZOMATO.NS"
    ],
    "US Tech Giants": ["NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "PLTR", "COIN"],
    "Crypto (24x7)": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"]
}

# Top Controls
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    market_choice = st.selectbox("Market Segment Chunein:", list(WATCHLISTS.keys()))

with col2:
    risk_budget = st.number_input("Max Risk Per Option Trade (₹):", min_value=500, max_value=50000, value=1500, step=500)

with col3:
    auto_refresh = st.checkbox("Auto-Sync (60s) ⏱️", value=True)

# -------------------------------------------------------------
# OPTION STRIKE CALCULATOR HELPER
# -------------------------------------------------------------
def get_atm_strike(index_name, spot_price):
    if "NIFTY 50" in index_name:
        step = 50
        lot_size = 25  # Latest Nifty contract lot size
    elif "BANK NIFTY" in index_name:
        step = 100
        lot_size = 15  # Latest Bank Nifty lot size
    else:
        step = 50
        lot_size = 40
    atm_strike = int(round(spot_price / step) * step)
    return atm_strike, lot_size

# -------------------------------------------------------------
# SCANNER LOGIC
# -------------------------------------------------------------
@st.cache_data(ttl=30)
def fetch_and_scan(tickers, market_type, risk_amount):
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
            low_25 = float(df['Low'].iloc[-25:-1].min())
            vol = float(df['Volume'].iloc[-1])
            avg_vol = float(df['Volume'].iloc[-25:-1].mean()) or 1.0

            rvol = round(vol / avg_vol, 2) if avg_vol > 0 else 1.0

            atr_series = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            atr = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else (close * 0.005)

            rsi_series = ta.momentum.rsi(df['Close'], window=14)
            rsi = round(float(rsi_series.dropna().iloc[-1]), 1) if not rsi_series.dropna().empty else 50.0

            # Signal Check: Bullish Breakout vs Bearish Breakdown
            is_bullish = (close > high_25) and (close > open_p)
            is_bearish = (close < low_25) and (close < open_p)

            # Name mapping
            name_map = {
                "^NSEI": "NIFTY 50",
                "^NSEBANK": "BANK NIFTY",
                "NIFTY_FIN_SERVICE.NS": "FIN NIFTY",
                "GC=F": "XAUUSD (Gold)",
                "SI=F": "XAGUSD (Silver)",
                "CL=F": "CRUDE OIL"
            }
            name = name_map.get(ticker, ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", ""))

            # Option Specific Mode
            if "Index Options" in market_type:
                atm_strike, lot_size = get_atm_strike(name, close)
                
                # Approximate Delta = 0.5 for ATM option
                opt_atr_pts = round(atr * 0.5, 1)
                opt_sl_pts = max(round(opt_atr_pts * 0.8, 1), 15.0)  # Standard points SL
                opt_target_pts = round(opt_sl_pts * 1.8, 1)          # 1:1.8 Risk:Reward

                risk_per_lot = opt_sl_pts * lot_size
                recommended_lots = max(1, int(risk_amount / risk_per_lot))

                if is_bullish:
                    signal = f"🟢 BUY {atm_strike} CE"
                    priority = 0
                elif is_bearish:
                    signal = f"🔴 BUY {atm_strike} PE"
                    priority = 0
                else:
                    signal = "⚪ NO SETUP (RANGE)"
                    priority = 1

                results.append({
                    "Priority": priority,
                    "Index": name,
                    "Spot LTP": round(close, 2),
                    "Actionable Option": signal,
                    "Option SL": f"-{opt_sl_pts} pts",
                    "Option Target": f"+{opt_target_pts} pts",
                    "Recommended Lots": f"{recommended_lots} Lot ({recommended_lots * lot_size} Qty)",
                    "Max Risk": f"₹{int(risk_per_lot * recommended_lots)}",
                    "RSI": rsi,
                    "Chart": f"https://in.tradingview.com/chart/?symbol={name.replace(' ', '')}"
                })
            else:
                # Regular Equity/Forex Mode
                sl = round(close - (1.0 * atr), 2 if "=" not in ticker else 4)
                tp = round(close + (1.5 * atr), 2 if "=" not in ticker else 4)
                currency = "₹" if ".NS" in ticker or ticker == "^NSEI" else "$"
                
                results.append({
                    "Priority": 0 if is_bullish else 1,
                    "Asset": name,
                    "Signal": "🟢 BUY BREAKOUT" if is_bullish else "⚪ CONSOLIDATION",
                    "LTP": f"{currency}{round(close, 2 if '=' not in ticker else 4)}",
                    "Stop-Loss": f"{currency}{sl}",
                    "Target": f"{currency}{tp}",
                    "RSI": rsi,
                    "RVol": f"{rvol}x",
                    "Chart": f"https://in.tradingview.com/chart/?symbol={name.replace(' ', '')}"
                })
        except Exception:
            continue

    df_out = pd.DataFrame(results)
    if not df_out.empty:
        df_out = df_out.sort_values(by=["Priority"]).drop(columns=["Priority"])
    return df_out

with st.spinner("Index Levels & Option Strike Analysis Chalu Hai..."):
    df_results = fetch_and_scan(WATCHLISTS[market_choice], market_choice, risk_budget)

if not df_results.empty:
    st.dataframe(
        df_results,
        column_config={
            "Chart": st.column_config.LinkColumn("TradingView", display_text="Open Chart ↗")
        },
        use_container_width=True,
        height=550
    )
else:
    st.info("Market data load ho raha hai. Thoda wait karein.")

if auto_refresh:
    time.sleep(60)
    st.rerun()
