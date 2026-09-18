import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import ta
from datetime import datetime, timezone, timedelta

# Page Configuration
st.set_page_config(
    page_title="Institutional Grade Trading Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Styling
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background-color: #1a1c24;
        border-radius: 8px;
        padding: 15px;
        border: 1px solid #2d3139;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# WATCHLIST DICTIONARY
# -------------------------------------------------------------
MARKET_UNIVERSES = {
    "Index Options (Intraday)": ["^NSEI", "^NSEBANK"],
    "Indian Equities (NSE)": [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS",
        "KOTAKBANK.NS", "LT.NS", "BHARTIARTL.NS", "ITC.NS", "HINDUNILVR.NS", "TATAMOTORS.NS", "MARUTI.NS",
        "M&M.NS", "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
        "TITAN.NS", "BAJFINANCE.NS", "ADANIENT.NS", "ADANIPORTS.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS",
        "SUZLON.NS", "IREDA.NS", "RVNL.NS", "IRFC.NS", "IRCON.NS", "RAILTEL.NS", "MAZDOCK.NS", "COCHINSHIP.NS",
        "HAL.NS", "BEL.NS", "BDL.NS", "BHEL.NS", "HUDCO.NS", "NBCC.NS", "SAIL.NS", "NMDC.NS", "NATIONALUM.NS",
        "BSE.NS", "CDSL.NS", "ANGELONE.NS", "MCX.NS", "TATATECH.NS", "TRENT.NS", "ZOMATO.NS", "JIOFIN.NS",
        "DIXON.NS", "POLYCAB.NS", "KEI.NS", "KALYANKJIL.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "PERSISTENT.NS",
        "COFORGE.NS", "DLF.NS", "LODHA.NS", "AUROPHARMA.NS", "LUPIN.NS", "EXIDEIND.NS", "ASHOKLEY.NS"
    ],
    "US Equities (NASDAQ/NYSE)": [
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "NFLX", "PLTR",
        "AVGO", "SMCI", "ARM", "QCOM", "INTC", "MU", "PANW", "CRWD", "COIN", "MSTR"
    ],
    "Forex & Commodities": [
        "GC=F", "SI=F", "CL=F", "HG=F", "INR=X", "EURUSD=X", 
        "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"
    ],
    "Crypto (24x7)": [
        "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD",
        "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "SUI-USD"
    ]
}

NAME_MAP = {
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "GC=F": "XAUUSD (Gold)",
    "SI=F": "XAGUSD (Silver)",
    "CL=F": "CRUDE OIL",
    "HG=F": "COPPER",
    "INR=X": "USD/INR",
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD",
    "USDCHF=X": "USD/CHF",
    "NZDUSD=X": "NZD/USD",
    "BTC-USD": "BITCOIN",
    "ETH-USD": "ETHEREUM",
    "SOL-USD": "SOLANA"
}

def calculate_vwap(df):
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    vol = df['Volume'].replace(0, 1)
    return (typical_price * vol).cumsum() / vol.cumsum()

# -------------------------------------------------------------
# TOP CONTROLS & HEADER
# -------------------------------------------------------------
st.title("⚡ Institutional Grade Trading Terminal")

col1, col2, col3, col4 = st.columns([2, 1.5, 1, 1])

with col1:
    selected_universe = st.selectbox(
        "Active Asset Universe:",
        list(MARKET_UNIVERSES.keys()),
        index=3  # Defaults to Forex & Commodities as in dashboard
    )

with col2:
    risk_per_trade = st.number_input(
        "Max Risk Per Position (₹ / $):",
        min_value=100,
        max_value=50000,
        value=1500,
        step=100
    )

with col3:
    audio_chime = st.checkbox("Audio Chime 🔔", value=False)

with col4:
    auto_sync = st.checkbox("Auto-Sync (60s) 🔄", value=True)

# -------------------------------------------------------------
# DATA ENGINE & SCANNER
# -------------------------------------------------------------
tickers = MARKET_UNIVERSES[selected_universe]

@st.cache_data(ttl=60)
def fetch_market_data(ticker_list):
    try:
        data = yf.download(ticker_list, period="5d", interval="15m", group_by='ticker', progress=False)
        return data
    except Exception:
        return None

raw_data = fetch_market_data(tickers)

records = []
active_breakouts = 0

if raw_data is not None:
    for ticker in tickers:
        try:
            df = raw_data[ticker] if len(tickers) > 1 else raw_data
            df = df.dropna()
            if len(df) < 25:
                continue

            c_close = float(df['Close'].iloc[-1])
            c_open = float(df['Open'].iloc[-1])
            c_vol = float(df['Volume'].iloc[-1])

            df['VWAP'] = calculate_vwap(df)
            c_vwap = float(df['VWAP'].iloc[-1])

            prev_window = df.iloc[-25:-1]
            res_level = float(prev_window['High'].max())
            sup_level = float(prev_window['Low'].min())
            avg_vol = float(prev_window['Volume'].mean()) or 1.0

            atr_s = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            atr = float(atr_s.dropna().iloc[-1]) if not atr_s.dropna().empty else (c_close * 0.005)

            rsi_s = ta.momentum.rsi(df['Close'], window=14)
            rsi = float(rsi_s.dropna().iloc[-1]) if not rsi_s.dropna().empty else 50.0

            ema20_s = ta.trend.ema_indicator(df['Close'], window=20)
            ema20 = float(ema20_s.dropna().iloc[-1]) if not ema20_s.dropna().empty else c_close

            ema50_s = ta.trend.ema_indicator(df['Close'], window=50)
            ema50 = float(ema50_s.dropna().iloc[-1]) if not ema50_s.dropna().empty else c_close

            is_special = ("=" in ticker or "^" in ticker or "-USD" in ticker)
            rvol = (c_vol / avg_vol) if avg_vol > 0 else 1.0
            rvol_display = "Liquid" if is_special else f"{round(rvol, 2)}x"

            # -------------------------------------------------------------
            # SIGNAL & SETUP GRADING ENGINE
            # -------------------------------------------------------------
            is_breakout = (c_close > res_level) and (c_close > c_open) and (c_close > ema20)
            is_breakdown = (c_close < sup_level) and (c_close < c_open) and (c_close < ema20)

            if is_breakout:
                signal = "🟢 BUY BREAKOUT"
                active_breakouts += 1
                if (rvol >= 2.5 or is_special) and (c_close > ema50) and (rsi >= 58):
                    grade = "Grade A+ (High Conviction)"
                elif (rvol >= 1.6 or is_special) and (rsi >= 53):
                    grade = "Grade A (Institutional)"
                else:
                    grade = "Grade B (Momentum Scalp)"
            elif is_breakdown:
                signal = "🔴 SELL BREAKDOWN"
                active_breakouts += 1
                if (rvol >= 2.5 or is_special) and (c_close < ema50) and (rsi <= 42):
                    grade = "Grade A+ (High Conviction)"
                elif (rvol >= 1.6 or is_special) and (rsi <= 47):
                    grade = "Grade A (Institutional)"
                else:
                    grade = "Grade B (Momentum Scalp)"
            else:
                signal = "⚪ CONSOLIDATION"
                grade = "Neutral"

            # RRR Calculations (1:1 & 1:2 RRR)
            sl_dist = 1.0 * atr
            if "SELL" in signal:
                sl = c_close + sl_dist
                target_1 = c_close - (1.0 * sl_dist)
                target_2 = c_close - (2.0 * sl_dist)
            else:
                sl = c_close - sl_dist
                target_1 = c_close + (1.0 * sl_dist)
                target_2 = c_close + (2.0 * sl_dist)

            risk_per_unit = max(abs(c_close - sl), 0.0001)
            rec_size = max(1, int(risk_per_trade / risk_per_unit))

            display_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("-USD", ""))
            decimals = 4 if is_special and "USD" in ticker else 2

            records.append({
                "Asset": display_name,
                "Signal": signal,
                "Setup Grade": grade,
                "LTP": round(c_close, decimals),
                "Stop Loss": round(sl, decimals),
                "Target 1 (1:1)": round(target_1, decimals),
                "Target 2 (1:2)": round(target_2, decimals),
                "RVol": rvol_display,
                "RSI": round(rsi, 1),
                "Recommended Size": f"{rec_size} Units"
            })
        except Exception:
            continue

# -------------------------------------------------------------
# METRICS ROW
# -------------------------------------------------------------
m_col1, m_col2, m_col3 = st.columns(3)

with m_col1:
    st.metric("Universe Tracked", len(tickers))
with m_col2:
    st.metric("Active Breakouts", active_breakouts)
with m_col3:
    st.metric("Selected Segment", selected_universe)

st.markdown("---")

# -------------------------------------------------------------
# LIVE MONITORING TABLE
# -------------------------------------------------------------
if records:
    df_display = pd.DataFrame(records)
    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=False
    )
else:
    st.info("No active market data fetched for this universe. Check market hours or network connection.")
