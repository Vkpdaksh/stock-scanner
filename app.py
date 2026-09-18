import os
import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import yfinance as yf
import ta
from datetime import datetime, timezone, timedelta

# Page Setup (Default Clean Theme Preserved)
st.set_page_config(
    page_title="Institutional Trading Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

CONFIG_FILE = "system_mode.json"
PAPER_TRADES_FILE = "paper_trades.json"

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default

def save_json(filepath, data):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

# Load or initialize modes
system_config = load_json(CONFIG_FILE, {"mode": "Beginner (Safe)", "execution": "Paper Trading"})
paper_data = load_json(PAPER_TRADES_FILE, {"balance": 100000, "trades": []})

# -------------------------------------------------------------
# WATCHLISTS & SECTOR INDICES
# -------------------------------------------------------------
SECTOR_INDICES = {
    "NIFTY BANK": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "NIFTY AUTO": "^CNXAUTO",
    "NIFTY METAL": "^CNXMETAL",
    "NIFTY PHARMA": "^CNXPHARMA",
    "NIFTY ENERGY": "^CNXENERGY",
    "NIFTY FMCG": "^CNXFMCG",
    "NIFTY REALTY": "^CNXREALTY"
}

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
# TOP HEADER & PROFILE SWITCHER
# -------------------------------------------------------------
st.title("⚡ Institutional Trading Terminal")

col_mode, col_exec, col_risk = st.columns([1.5, 1.5, 1.2])

with col_mode:
    selected_mode = st.selectbox(
        "👤 Select Profile Mode:",
        ["Beginner (Safe)", "Pro Trader (Full)"],
        index=0 if system_config.get("mode") == "Beginner (Safe)" else 1
    )

is_beginner = (selected_mode == "Beginner (Safe)")

with col_exec:
    if is_beginner:
        selected_execution = st.selectbox("Execution Route:", ["Virtual Paper Trading (Locked)"], disabled=True)
        execution_type = "Paper Trading"
    else:
        selected_execution = st.selectbox(
            "Execution Route:",
            ["Real Fund (SmartAPI)", "Virtual Paper Trading"],
            index=0 if system_config.get("execution") == "Real Fund (SmartAPI)" else 1
        )
        execution_type = "SmartAPI" if "SmartAPI" in selected_execution else "Paper Trading"

with col_risk:
    risk_per_trade = st.number_input(
        "Risk Per Trade (₹ / $):",
        min_value=100,
        max_value=50000,
        value=1000 if is_beginner else 2000,
        step=100
    )

# Save configuration for Scanner Bot sync
if system_config.get("mode") != selected_mode or system_config.get("execution") != execution_type:
    system_config["mode"] = selected_mode
    system_config["execution"] = execution_type
    save_json(CONFIG_FILE, system_config)

st.caption(f"Profile: **{selected_mode}** | Execution: **{execution_type}** | Daily Cap: **{'3 Trades Max' if is_beginner else 'Unlimited Alerts'}**")

# -------------------------------------------------------------
# VIRTUAL PAPER TRADING PORTFOLIO BAR
# -------------------------------------------------------------
st.markdown("### 💼 Virtual Paper Trading Portfolio")
total_pnl = paper_data.get("balance", 100000) - 100000
trades_count = len(paper_data.get("trades", []))

p1, p2, p3 = st.columns(3)
with p1:
    st.metric("Virtual Balance", f"₹{paper_data.get('balance', 100000):,}")
with p2:
    st.metric("Total Paper P&L", f"₹{total_pnl:+,}", delta=f"₹{total_pnl:+,}")
with p3:
    st.metric("Total Paper Trades", trades_count)

st.write("")

# -------------------------------------------------------------
# SECTORAL MOMENTUM HEATMAP (COLORED CARDS)
# -------------------------------------------------------------
with st.expander("📊 Live Sectoral Momentum Heatmap (NSE)", expanded=True):
    try:
        sector_tickers = list(SECTOR_INDICES.values())
        sec_data = yf.download(sector_tickers, period="2d", interval="15m", group_by='ticker', progress=False)
        sec_cols = st.columns(len(SECTOR_INDICES))
        
        for idx, (sec_name, sec_sym) in enumerate(SECTOR_INDICES.items()):
            try:
                s_df = sec_data[sec_sym].dropna()
                curr = float(s_df['Close'].iloc[-1])
                prev = float(s_df['Close'].iloc[0])
                pct = ((curr - prev) / prev) * 100

                if pct >= 0:
                    bg_color, border_color, text_color, icon = "#e8f5e9", "#2e7d32", "#1b5e20", "▲"
                else:
                    bg_color, border_color, text_color, icon = "#ffebee", "#c62828", "#b71c1c", "▼"

                with sec_cols[idx]:
                    st.markdown(f"""
                        <div style="background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; padding: 8px 4px; text-align: center;">
                            <div style="font-size: 11px; font-weight: 700; color: #555555;">{sec_name.replace('NIFTY ', '')}</div>
                            <div style="font-size: 14px; font-weight: 800; color: #111111; margin: 2px 0;">{curr:.1f}</div>
                            <div style="font-size: 12px; font-weight: 700; color: {text_color};">{icon} {pct:+.2f}%</div>
                        </div>
                    """, unsafe_allow_html=True)
            except Exception:
                pass
    except Exception:
        st.caption("Sector radar loading...")

# -------------------------------------------------------------
# DATA ENGINE & SCANNER
# -------------------------------------------------------------
available_universes = list(MARKET_UNIVERSES.keys())
if is_beginner and "Index Options (Intraday)" in available_universes:
    available_universes.remove("Index Options (Intraday)")

selected_universe = st.selectbox("Active Asset Universe:", available_universes, index=0)
tickers = MARKET_UNIVERSES[selected_universe]

@st.cache_data(ttl=60)
def fetch_market_data(ticker_list):
    try:
        return yf.download(ticker_list, period="5d", interval="15m", group_by='ticker', progress=False)
    except Exception:
        return None

raw_data = fetch_market_data(tickers) if tickers else None
records = []

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

            ema20 = float(ta.trend.ema_indicator(df['Close'], window=20).dropna().iloc[-1])
            ema50 = float(ta.trend.ema_indicator(df['Close'], window=50).dropna().iloc[-1])

            is_special = ("=" in ticker or "^" in ticker or "-USD" in ticker)
            rvol = (c_vol / avg_vol) if avg_vol > 0 else 1.0
            rvol_display = "Liquid" if is_special else f"{round(rvol, 2)}x"

            is_breakout = (c_close > res_level) and (c_close > c_open) and (c_close > ema20)
            is_breakdown = (c_close < sup_level) and (c_close < c_open) and (c_close < ema20)

            if is_breakout:
                signal = "🟢 BUY BREAKOUT"
                trade_logic = f"Closed above resistance ({res_level:.2f}) with {rvol:.1f}x volume and VWAP support."
                if (rvol >= 2.5 or is_special) and (c_close > ema50) and (rsi >= 58):
                    grade = "Grade A+ (Sniper)"
                elif (rvol >= 1.6 or is_special) and (rsi >= 53):
                    grade = "Grade A (Inst.)"
                else:
                    grade = "Grade B (Scalp)"
            elif is_breakdown:
                signal = "🔴 SELL BREAKDOWN"
                trade_logic = f"Closed below support ({sup_level:.2f}) with negative pressure."
                if (rvol >= 2.5 or is_special) and (c_close < ema50) and (rsi <= 42):
                    grade = "Grade A+ (Sniper)"
                elif (rvol >= 1.6 or is_special) and (rsi <= 47):
                    grade = "Grade A (Inst.)"
                else:
                    grade = "Grade B (Scalp)"
            else:
                signal = "⚪ CONSOLIDATION"
                grade = "Neutral"
                trade_logic = "Price oscillating within range."

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
                "Ticker": ticker,
                "Asset": display_name,
                "Signal": signal,
                "Setup Grade": grade,
                "LTP": round(c_close, decimals),
                "Stop Loss": round(sl, decimals),
                "Target 1 (1:1)": round(target_1, decimals),
                "Target 2 (1:2)": round(target_2, decimals),
                "RVol": rvol_display,
                "RSI": round(rsi, 1),
                "Recommended Size": f"{rec_size} Units",
                "Why This Trade": trade_logic,
                "Size": rec_size
            })
        except Exception:
            continue

# -------------------------------------------------------------
# TABLE & EXECUTION DESK
# -------------------------------------------------------------
if records:
    df_display = pd.DataFrame(records).drop(columns=["Ticker", "Size"])
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("No active setups found in this universe.")

# Pro Trader Order Console
if not is_beginner and execution_type == "SmartAPI":
    st.markdown("### ⚡ Pro Real Fund SmartAPI Order Desk")
    ord1, ord2, ord3, ord4 = st.columns([2, 1.2, 1.2, 1.5])
    asset_names = [r["Asset"] for r in records] if records else []
    with ord1:
        chosen_asset = st.selectbox("Contract to Execute:", asset_names if asset_names else ["None"])
    selected_item = next((r for r in records if r["Asset"] == chosen_asset), None)
    with ord2:
        side = st.selectbox("Direction:", ["BUY", "SELL"])
    with ord3:
        suggested_qty = selected_item["Size"] if selected_item else 1
        qty_input = st.number_input("Lots/Units:", min_value=1, value=max(1, suggested_qty), step=1)
    with ord4:
        st.write("")
        st.write("")
        if st.button("🚀 Fire to Angel One", use_container_width=True):
            st.info("Direct SmartAPI order fired.")

# Interactive Chart
st.markdown("### 📈 Interactive TradingView Live Chart")
if records:
    clean_sym = records[0]["Ticker"].replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
    if clean_sym == "^NSEI": clean_sym = "NIFTY"
    elif clean_sym == "^NSEBANK": clean_sym = "BANKNIFTY"
    tv_code = f"""
    <div class="tradingview-widget-container" style="height:500px; width:100%;">
      <div id="tradingview_chart" style="height:500px;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{clean_sym}",
        "interval": "15",
        "timezone": "Asia/Kolkata",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "toolbar_bg": "#131722",
        "container_id": "tradingview_chart"
      }});
      </script>
    </div>
    """
    components.html(tv_code, height=510)
