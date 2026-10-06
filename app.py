import os
import json
import urllib.request
import urllib.parse
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone, timedelta
from streamlit_gsheets import GSheetsConnection

# -------------------------------------------------------------
# 1. PAGE SETUP & CONFIG
# -------------------------------------------------------------
st.set_page_config(
    page_title="SAHI Pro Trading Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def get_secret(key_name):
    try:
        if hasattr(st, "secrets") and key_name in st.secrets:
            return str(st.secrets[key_name])
    except Exception:
        pass
    return os.environ.get(key_name, "")

TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")
ANGEL_API_KEY = get_secret("ANGEL_API_KEY")
ANGEL_CLIENT_ID = get_secret("ANGEL_CLIENT_ID")
ANGEL_MPIN = get_secret("ANGEL_MPIN")
ANGEL_TOTP_KEY = get_secret("ANGEL_TOTP_KEY")

# -------------------------------------------------------------
# 2. GOOGLE SHEETS CLOUD STORAGE (PERSISTENT DATA)
# -------------------------------------------------------------
@st.cache_resource
def get_sheets_connection():
    return st.connection("gsheets", type=GSheetsConnection)

SHEET_COLUMNS = [
    "id", "date", "asset", "type", "entry", "sl", "tp1", "tp2", 
    "qty", "invested_capital", "status", "timeframe", "exit_price", "exit_time", "pnl"
]

def load_sheet_trades():
    try:
        conn = get_sheets_connection()
        df = conn.read(ttl="0s")
        if df is None or df.empty:
            return pd.DataFrame(columns=SHEET_COLUMNS)
        for col in SHEET_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame(columns=SHEET_COLUMNS)

def save_sheet_trades(df):
    try:
        conn = get_sheets_connection()
        conn.update(data=df)
        return True
    except Exception as e:
        st.error(f"Google Sheets Error: {str(e)}")
        return False

# -------------------------------------------------------------
# 3. HELPER FUNCTIONS & TIME
# -------------------------------------------------------------
def get_ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

ist_now = get_ist_now()
today_date_str = ist_now.strftime("%Y-%m-%d")
time_str = ist_now.strftime("%I:%M:%S %p IST")
cur_mins = ist_now.hour * 60 + ist_now.minute

# -------------------------------------------------------------
# 4. ROBUST TICKER MAPPINGS (ALL MARKETS)
# -------------------------------------------------------------
FOREX_MAP = {
    "AUD/USD": "AUDUSD=X", "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X", "USD/CAD": "USDCAD=X", "USD/CHF": "USDCHF=X",
    "NZD/USD": "NZDUSD=X", "EUR/GBP": "EURGBP=X", "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X", "USD/INR": "INR=X", "GOLD (XAUUSD)": "GC=F",
    "SILVER (XAGUSD)": "SI=F", "CRUDE OIL": "CL=F", "COPPER": "HG=F", "NATURAL GAS": "NG=F"
}

CRYPTO_MAP = {
    "BITCOIN": "BTC-USD", "ETHEREUM": "ETH-USD", "SOLANA": "SOL-USD",
    "XRP": "XRP-USD", "BINANCE COIN": "BNB-USD", "DOGECOIN": "DOGE-USD",
    "CARDANO": "ADA-USD", "AVALANCHE": "AVAX-USD", "CHAINLINK": "LINK-USD", "SUI": "SUI-USD"
}

INDEX_MAP = {
    "NIFTY 50": "^NSEI", "BANK NIFTY": "^NSEBANK"
}

MARKET_CATEGORIES = {
    "Indian Equities & Indices (NSE)": [
        "NIFTY 50", "BANK NIFTY", "RELIANCE", "TCS", "INFOSYS", "HDFCBANK", "ICICIBANK", "SBIN",
        "TATAMOTORS", "MARUTI", "M&M", "HAL", "BEL", "RVNL", "IRFC", "TATASTEEL", "JSWSTEEL",
        "ANGELONE", "BSE", "CDSL", "MCX", "ZOMATO", "TITAN", "ITC", "BHARTIARTL"
    ],
    "Forex & Commodities": list(FOREX_MAP.keys()),
    "US Equities (NASDAQ/NYSE)": ["AMZN", "GOOGL", "NVDA", "TSLA", "AAPL", "MSFT", "META", "AMD", "NFLX", "PLTR", "AVGO", "SMCI", "COIN", "MSTR"],
    "Crypto (24x7)": list(CRYPTO_MAP.keys())
}

def resolve_ticker(asset_label):
    if asset_label in FOREX_MAP:
        return FOREX_MAP[asset_label]
    if asset_label in CRYPTO_MAP:
        return CRYPTO_MAP[asset_label]
    if asset_label in INDEX_MAP:
        return INDEX_MAP[asset_label]
    
    clean = asset_label.replace(".NS", "").replace("^", "").strip()
    if clean == "INFOSYS":
        return "INFY.NS"
    if clean in MARKET_CATEGORIES["Indian Equities & Indices (NSE)"]:
        return f"{clean}.NS"
    return clean

@st.cache_data(ttl=30)
def fetch_chart_dataframe(ticker, tf_str):
    interval_map = {"5m": "5m", "15m": "15m", "60m": "1h", "D": "1d"}
    period_map = {"5m": "5d", "15m": "5d", "60m": "1mo", "D": "1y"}
    inv = interval_map.get(tf_str, "1h")
    prd = period_map.get(tf_str, "1mo")
    try:
        df = yf.download(ticker, period=prd, interval=inv, progress=False)
        if not df.empty:
            df = df.dropna()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
    except Exception:
        pass
    return pd.DataFrame()

# -------------------------------------------------------------
# 5. HEADER & CONTROLS
# -------------------------------------------------------------
st.title("⚡ SAHI Pro Trading Terminal")

all_market_keys = list(MARKET_CATEGORIES.keys())
col_mkt, col_tf, col_mode = st.columns([1.8, 1.2, 1.2])

with col_mkt:
    selected_universe = st.selectbox("🌐 Asset Universe:", all_market_keys, index=0)

with col_tf:
    chart_interval = st.selectbox("⏱️ Timeframe:", ["5m", "15m", "60m", "D"], index=2)

with col_mode:
    selected_mode = st.selectbox("👤 Profile Mode:", ["Beginner (Safe)", "Pro Trader (Full)"], index=1)

tickers_in_univ = MARKET_CATEGORIES[selected_universe]

sheet_trades_df = load_sheet_trades()
all_trades = sheet_trades_df.to_dict(orient="records") if not sheet_trades_df.empty else []
open_trades = [t for t in all_trades if str(t.get("status", "")).upper() == "OPEN"]
closed_trades = [t for t in all_trades if str(t.get("status", "")).upper() not in ["OPEN", ""]]

INITIAL_BASE_CAPITAL = 10000.0
blocked_capital = sum([float(t.get("invested_capital", 0.0) or 0.0) for t in open_trades])
realized_closed_pnl = sum([float(t.get("pnl", 0.0) or 0.0) for t in closed_trades])
available_balance = INITIAL_BASE_CAPITAL + realized_closed_pnl - blocked_capital

# -------------------------------------------------------------
# 6. AUTO SL & TARGET MONITOR
# -------------------------------------------------------------
sheet_modified = False
for trade in all_trades:
    if str(trade.get("status", "")).upper() == "OPEN":
        t_id = trade.get("id")
        a_name = trade.get("asset")
        resolved_sym = resolve_ticker(a_name)
        df_check = fetch_chart_dataframe(resolved_sym, "60m")
        
        if not df_check.empty:
            c_ltp = float(df_check['Close'].iloc[-1])
            c_high = float(df_check['High'].iloc[-1])
            c_low = float(df_check['Low'].iloc[-1])
            
            e_price = float(trade.get("entry", 0.0))
            s_price = float(trade.get("sl", 0.0))
            t_price = float(trade.get("tp1", 0.0))
            q = int(trade.get("qty", 1))
            side_type = str(trade.get("type", "BUY")).upper()

            if side_type == "BUY":
                tp_hit = (c_high >= t_price) or (c_ltp >= t_price)
                sl_hit = (c_low <= s_price) or (c_ltp <= s_price)
            else:
                tp_hit = (c_low <= t_price) or (c_ltp <= t_price)
                sl_hit = (c_high >= s_price) or (c_ltp >= s_price)

            if sl_hit or tp_hit:
                status_val = "TARGET_HIT (1:2)" if tp_hit else "SL_HIT"
                exit_price_val = t_price if tp_hit else s_price
                pnl_realized = (exit_price_val - e_price) * q if side_type == "BUY" else (e_price - exit_price_val) * q
                idx_list = sheet_trades_df.index[sheet_trades_df["id"] == t_id].tolist()
                if idx_list:
                    row_idx = idx_list[0]
                    sheet_trades_df.at[row_idx, "status"] = status_val
                    sheet_trades_df.at[row_idx, "exit_price"] = exit_price_val
                    sheet_trades_df.at[row_idx, "exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
                    sheet_trades_df.at[row_idx, "pnl"] = pnl_realized
                    sheet_modified = True

if sheet_modified:
    save_sheet_trades(sheet_trades_df)
    st.rerun()

# -------------------------------------------------------------
# 7. SINGLE-SCREEN TRADING DESK (PRO CANDLESTICK ENGINE)
# -------------------------------------------------------------
st.markdown("### 🖥️ Single-Screen Trading Desk")
desk_left, desk_right = st.columns([2.3, 1.2])

with desk_left:
    active_chart_asset = st.selectbox("Active Asset:", tickers_in_univ, index=0, key="screen_asset_sel")
    active_ticker = resolve_ticker(active_chart_asset)
    
    df_chart = fetch_chart_dataframe(active_ticker, chart_interval)
    
    if not df_chart.empty:
        # EMA 20 Calculation
        df_chart['EMA20'] = df_chart['Close'].ewm(span=20, adjust=False).mean()

        # Candlestick + Volume Subplot Figure
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.03, 
            subplot_titles=(f"{active_chart_asset} ({active_ticker}) - Live {chart_interval} Candlestick Chart", "Volume"),
            row_width=[0.2, 0.8]
        )

        # 1. Candlestick Bars
        fig.add_trace(go.Candlestick(
            x=df_chart.index,
            open=df_chart['Open'],
            high=df_chart['High'],
            low=df_chart['Low'],
            close=df_chart['Close'],
            name="Price",
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350'
        ), row=1, col=1)

        # 2. EMA 20 Overlay Line
        fig.add_trace(go.Scatter(
            x=df_chart.index,
            y=df_chart['EMA20'],
            line=dict(color='#ff9800', width=1.5),
            name="EMA 20"
        ), row=1, col=1)

        # 3. Volume Bars
        vol_colors = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(df_chart['Close'], df_chart['Open'])]
        fig.add_trace(go.Bar(
            x=df_chart.index,
            y=df_chart['Volume'],
            marker_color=vol_colors,
            name="Volume",
            showlegend=False
        ), row=2, col=1)

        fig.update_layout(
            template="plotly_dark",
            height=530,
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis_rangeslider_visible=False,
            paper_bgcolor="#131722",
            plot_bgcolor="#131722"
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning(f"Connecting market feed for {active_chart_asset}... Please wait.")

with desk_right:
    st.markdown("#### ⚡ 1-Click Fast Execution")
    
    if not df_chart.empty:
        asset_ltp = float(df_chart['Close'].iloc[-1])
        atr_s = ta.volatility.average_true_range(df_chart['High'], df_chart['Low'], df_chart['Close'], window=14)
        atr_val = float(atr_s.dropna().iloc[-1]) if not atr_s.dropna().empty else (asset_ltp * 0.01)
    else:
        asset_ltp = 100.0
        atr_val = 1.0

    is_fx = any(x in active_ticker for x in ["=X", "=F", "-USD"]) or ("/" in active_chart_asset)
    dec_fmt = "%.4f" if (is_fx and asset_ltp < 20) else "%.2f"
    step_val = 0.0001 if (is_fx and asset_ltp < 20) else 0.05
    curr_prefix = "$" if selected_universe == "US Equities (NASDAQ/NYSE)" else ("₹" if "NSE" in selected_universe else "")

    # Strict 1:2 R:R Formula
    sl_dist = 1.0 * atr_val
    auto_sl_buy = round(asset_ltp - sl_dist, 4 if (is_fx and asset_ltp < 20) else 2)
    auto_tp_buy = round(asset_ltp + (2.0 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)
    auto_tp2_buy = round(asset_ltp + (3.5 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)

    st.metric(f"{active_chart_asset} Live Price", f"{curr_prefix}{dec_fmt % asset_ltp}")

    fast_qty = st.number_input("Lots / Qty:", min_value=1, value=1, step=1)
    req_fund = asset_ltp * fast_qty

    col_sl_b, col_tp_b = st.columns(2)
    with col_sl_b:
        exec_sl = st.number_input("Auto SL (1x ATR):", value=float(auto_sl_buy), step=step_val, format=dec_fmt)
    with col_tp_b:
        exec_tp = st.number_input("Auto Target (1:2):", value=float(auto_tp_buy), step=step_val, format=dec_fmt)

    st.caption(f"🔒 Required: ₹{req_fund:,.2f} | Balance: ₹{available_balance:,.2f}")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🟢 BUY (Mkt)", use_container_width=True):
            if req_fund > available_balance:
                st.error("Insufficient Balance!")
            else:
                new_id = int(sheet_trades_df["id"].max() + 1) if not sheet_trades_df.empty and pd.notnull(sheet_trades_df["id"].max()) else 1
                row = pd.DataFrame([{
                    "id": new_id, "date": ist_now.strftime("%Y-%m-%d %H:%M"),
                    "asset": active_chart_asset, "type": "BUY", "entry": asset_ltp,
                    "sl": exec_sl, "tp1": exec_tp, "tp2": auto_tp2_buy,
                    "qty": fast_qty, "invested_capital": req_fund,
                    "status": "OPEN", "timeframe": chart_interval, "exit_price": 0.0, "exit_time": "", "pnl": 0.0
                }])
                save_sheet_trades(pd.concat([sheet_trades_df, row], ignore_index=True))
                st.success("Buy Filled & Recorded in Google Sheet!")
                st.rerun()

    with col_btn2:
        if st.button("🔴 SELL (Mkt)", use_container_width=True):
            if req_fund > available_balance:
                st.error("Insufficient Balance!")
            else:
                auto_sl_sell = round(asset_ltp + sl_dist, 4 if (is_fx and asset_ltp < 20) else 2)
                auto_tp_sell = round(asset_ltp - (2.0 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)
                auto_tp2_sell = round(asset_ltp - (3.5 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)
                new_id = int(sheet_trades_df["id"].max() + 1) if not sheet_trades_df.empty and pd.notnull(sheet_trades_df["id"].max()) else 1
                row = pd.DataFrame([{
                    "id": new_id, "date": ist_now.strftime("%Y-%m-%d %H:%M"),
                    "asset": active_chart_asset, "type": "SELL", "entry": asset_ltp,
                    "sl": auto_sl_sell, "tp1": auto_tp_sell, "tp2": auto_tp2_sell,
                    "qty": fast_qty, "invested_capital": req_fund,
                    "status": "OPEN", "timeframe": chart_interval, "exit_price": 0.0, "exit_time": "", "pnl": 0.0
                }])
                save_sheet_trades(pd.concat([sheet_trades_df, row], ignore_index=True))
                st.success("Sell Filled & Recorded in Google Sheet!")
                st.rerun()

    st.markdown("---")
    st.markdown("##### 💼 Live Running Positions")
    if open_trades:
        for idx, tr in enumerate(open_trades):
            raw_pos_sym = resolve_ticker(tr.get('asset'))
            df_pos = fetch_chart_dataframe(raw_pos_sym, "60m")
            c_val = float(df_pos['Close'].iloc[-1]) if not df_pos.empty else float(tr.get('entry'))
            e_val = float(tr.get('entry'))
            q_val = int(tr.get('qty'))
            is_buy = str(tr.get('type')).upper() == "BUY"
            live_pnl = (c_val - e_val) * q_val if is_buy else (e_val - c_val) * q_val
            pnl_c = "#2e7d32" if live_pnl >= 0 else "#c62828"

            st.markdown(f"""
            <div style="background-color: #1a1e29; padding: 8px; border-radius: 5px; margin-bottom: 6px; border-left: 4px solid {pnl_c};">
                <div style="display:flex; justify-content:space-between;">
                    <b>{tr.get('asset')}</b>
                    <span style="color:{pnl_c}; font-weight:bold;">₹{live_pnl:+,.2f}</span>
                </div>
                <div style="font-size:11px; color:#90caf9;">Qty: {q_val} | Entry: {e_val:.2f} | LTP: {c_val:.2f}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Exit Position #{idx+1}", key=f"fast_exit_{tr.get('id')}", use_container_width=True):
                idx_l = sheet_trades_df.index[sheet_trades_df["id"] == tr.get('id')].tolist()
                if idx_l:
                    sheet_trades_df.at[idx_l[0], "status"] = "MANUAL_EXIT"
                    sheet_trades_df.at[idx_l[0], "exit_price"] = c_val
                    sheet_trades_df.at[idx_l[0], "exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
                    sheet_trades_df.at[idx_l[0], "pnl"] = live_pnl
                    save_sheet_trades(sheet_trades_df)
                    st.rerun()
    else:
        st.caption("No running positions right now.")
