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

# -------------------------------------------------------------
# 2. GOOGLE SHEETS CLOUD STORAGE (NEVER WIPES OUT)
# -------------------------------------------------------------
@st.cache_resource
def get_sheets_connection():
    return st.connection("gsheets", type=GSheetsConnection)

SHEET_COLUMNS = [
    "id", "date", "asset", "type", "entry", "sl", "tp1", "tp2", 
    "qty", "invested_capital", "status", "timeframe", "exit_price", "exit_time", "pnl", "partial_booked"
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
        st.error(f"Error saving to Google Sheets: {str(e)}")
        return False

# -------------------------------------------------------------
# 3. HELPER FUNCTIONS & IST TIME CALCULATION
# -------------------------------------------------------------
def get_ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

ist_now = get_ist_now()
today_date_str = ist_now.strftime("%Y-%m-%d")
time_str = ist_now.strftime("%I:%M:%S %p IST")
cur_mins = ist_now.hour * 60 + ist_now.minute
weekday = ist_now.weekday()

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
    "US Equities (NASDAQ/NYSE)": ["AMZN", "GOOGL", "NVDA", "TSLA", "AAPL", "MSFT", "META", "AMD", "NFLX", "PLTR", "AVGO", "SMCI", "COIN", "MSTR"],
    "Forex & Commodities": list(FOREX_MAP.keys()),
    "Crypto (24x7)": list(CRYPTO_MAP.keys())
}

def resolve_ticker(asset_label):
    if asset_label in FOREX_MAP:
        return FOREX_MAP[asset_label]
    if asset_label in CRYPTO_MAP:
        return CRYPTO_MAP[asset_label]
    if asset_label in INDEX_MAP:
        return INDEX_MAP[asset_label]
    
    clean = str(asset_label).replace(".NS", "").replace("^", "").strip()
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
# 5. HEADER & TIME-BASED MARKET AUTO-DETECTION
# -------------------------------------------------------------
st.title("⚡ SAHI Pro Trading Terminal")

all_market_keys = list(MARKET_CATEGORIES.keys())

# Real-time Market Timing Routing
if weekday < 5:
    if 555 <= cur_mins <= 930:        # 09:15 AM - 03:30 PM IST (NSE)
        auto_market_key = "Indian Equities & Indices (NSE)"
        active_session_badge = "🟢 NSE LIVE ACTIVE"
    elif 930 < cur_mins <= 1140:       # 03:30 PM - 07:00 PM IST (Commodities)
        auto_market_key = "Forex & Commodities"
        active_session_badge = "🟡 FOREX / COMMODITIES ACTIVE"
    elif cur_mins > 1140 or cur_mins <= 120:  # 07:00 PM - 02:00 AM IST (US)
        auto_market_key = "US Equities (NASDAQ/NYSE)"
        active_session_badge = "🔵 US MARKET LIVE ACTIVE"
    else:
        auto_market_key = "Crypto (24x7)"
        active_session_badge = "🟣 CRYPTO 24x7 ACTIVE"
else:
    auto_market_key = "Crypto (24x7)"
    active_session_badge = "🟣 WEEKEND / CRYPTO 24x7 ACTIVE"

default_mkt_index = all_market_keys.index(auto_market_key)

st.caption(f"Status: **{active_session_badge}** | Live IST Time: **{time_str}** | Features: **Auto SL/TP + Trailing to Cost + MTF Sync**")

col_mkt, col_tf, col_mode = st.columns([1.8, 1.2, 1.2])

with col_mkt:
    selected_universe = st.selectbox("🌐 Asset Universe:", all_market_keys, index=default_mkt_index)

with col_tf:
    chart_interval = st.selectbox("⏱️ Timeframe:", ["5m", "15m", "60m", "D"], index=2)

with col_mode:
    selected_mode = st.selectbox("👤 Profile Mode:", ["Beginner (Safe)", "Pro Trader (Full)"], index=1)

tickers_in_univ = MARKET_CATEGORIES[selected_universe]

sheet_trades_df = load_sheet_trades()
all_trades = sheet_trades_df.to_dict(orient="records") if not sheet_trades_df.empty else []
open_trades = [t for t in all_trades if str(t.get("status", "")).upper() in ["OPEN", "PARTIAL_BOOKED"]]
closed_trades = [t for t in all_trades if str(t.get("status", "")).upper() not in ["OPEN", "PARTIAL_BOOKED", ""]]

INITIAL_BASE_CAPITAL = 10000.0
blocked_capital = sum([float(t.get("invested_capital", 0.0) or 0.0) for t in open_trades])
realized_closed_pnl = sum([float(t.get("pnl", 0.0) or 0.0) for t in closed_trades])
available_balance = INITIAL_BASE_CAPITAL + realized_closed_pnl - blocked_capital

# -------------------------------------------------------------
# 6. AUTO MONITOR: PARTIAL PROFIT & TRAILING SL TO COST
# -------------------------------------------------------------
sheet_modified = False
for trade in all_trades:
    status_curr = str(trade.get("status", "")).upper()
    if status_curr in ["OPEN", "PARTIAL_BOOKED"]:
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
            t1_price = float(trade.get("tp1", 0.0))
            t2_price = float(trade.get("tp2", 0.0))
            q_total = int(trade.get("qty", 1))
            is_partial = str(trade.get("partial_booked", "NO")).upper() == "YES"
            side_type = str(trade.get("type", "BUY")).upper()

            idx_list = sheet_trades_df.index[sheet_trades_df["id"] == t_id].tolist()
            if not idx_list:
                continue
            row_idx = idx_list[0]

            if side_type == "BUY":
                # Check Target 1 Hit -> 50% Partial Book
                if not is_partial and (c_high >= t1_price or c_ltp >= t1_price):
                    booked_qty = max(1, q_total // 2)
                    rem_qty = q_total - booked_qty
                    partial_pnl = (t1_price - e_price) * booked_qty
                    
                    sheet_trades_df.at[row_idx, "status"] = "PARTIAL_BOOKED" if rem_qty > 0 else "TARGET_HIT (1:2)"
                    sheet_trades_df.at[row_idx, "partial_booked"] = "YES"
                    sheet_trades_df.at[row_idx, "pnl"] = float(trade.get("pnl", 0.0) or 0.0) + partial_pnl
                    sheet_trades_df.at[row_idx, "qty"] = rem_qty if rem_qty > 0 else booked_qty
                    sheet_trades_df.at[row_idx, "invested_capital"] = rem_qty * e_price
                    sheet_trades_df.at[row_idx, "sl"] = e_price  # Trailed to cost
                    sheet_modified = True
                    continue

                # Check Target 2 Hit (Extended 1:3.5)
                elif is_partial and (c_high >= t2_price or c_ltp >= t2_price):
                    rem_qty = int(sheet_trades_df.at[row_idx, "qty"])
                    t2_pnl = (t2_price - e_price) * rem_qty
                    sheet_trades_df.at[row_idx, "status"] = "TARGET_2_HIT (1:3.5)"
                    sheet_trades_df.at[row_idx, "exit_price"] = t2_price
                    sheet_trades_df.at[row_idx, "exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
                    sheet_trades_df.at[row_idx, "pnl"] = float(sheet_trades_df.at[row_idx, "pnl"] or 0.0) + t2_pnl
                    sheet_modified = True

                # Check Stop Loss Hit
                elif c_low <= s_price or c_ltp <= s_price:
                    rem_qty = int(sheet_trades_df.at[row_idx, "qty"])
                    sl_pnl = (s_price - e_price) * rem_qty
                    sheet_trades_df.at[row_idx, "status"] = "TRAILED_SL_COST" if is_partial else "SL_HIT"
                    sheet_trades_df.at[row_idx, "exit_price"] = s_price
                    sheet_trades_df.at[row_idx, "exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
                    sheet_trades_df.at[row_idx, "pnl"] = float(sheet_trades_df.at[row_idx, "pnl"] or 0.0) + sl_pnl
                    sheet_modified = True

            else:  # SELL Side
                if not is_partial and (c_low <= t1_price or c_ltp <= t1_price):
                    booked_qty = max(1, q_total // 2)
                    rem_qty = q_total - booked_qty
                    partial_pnl = (e_price - t1_price) * booked_qty
                    
                    sheet_trades_df.at[row_idx, "status"] = "PARTIAL_BOOKED" if rem_qty > 0 else "TARGET_HIT (1:2)"
                    sheet_trades_df.at[row_idx, "partial_booked"] = "YES"
                    sheet_trades_df.at[row_idx, "pnl"] = float(trade.get("pnl", 0.0) or 0.0) + partial_pnl
                    sheet_trades_df.at[row_idx, "qty"] = rem_qty if rem_qty > 0 else booked_qty
                    sheet_trades_df.at[row_idx, "invested_capital"] = rem_qty * e_price
                    sheet_trades_df.at[row_idx, "sl"] = e_price
                    sheet_modified = True
                    continue

                elif is_partial and (c_low <= t2_price or c_ltp <= t2_price):
                    rem_qty = int(sheet_trades_df.at[row_idx, "qty"])
                    t2_pnl = (e_price - t2_price) * rem_qty
                    sheet_trades_df.at[row_idx, "status"] = "TARGET_2_HIT (1:3.5)"
                    sheet_trades_df.at[row_idx, "exit_price"] = t2_price
                    sheet_trades_df.at[row_idx, "exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
                    sheet_trades_df.at[row_idx, "pnl"] = float(sheet_trades_df.at[row_idx, "pnl"] or 0.0) + t2_pnl
                    sheet_modified = True

                elif c_high >= s_price or c_ltp >= s_price:
                    rem_qty = int(sheet_trades_df.at[row_idx, "qty"])
                    sl_pnl = (e_price - s_price) * rem_qty
                    sheet_trades_df.at[row_idx, "status"] = "TRAILED_SL_COST" if is_partial else "SL_HIT"
                    sheet_trades_df.at[row_idx, "exit_price"] = s_price
                    sheet_trades_df.at[row_idx, "exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
                    sheet_trades_df.at[row_idx, "pnl"] = float(sheet_trades_df.at[row_idx, "pnl"] or 0.0) + sl_pnl
                    sheet_modified = True

if sheet_modified:
    save_sheet_trades(sheet_trades_df)
    st.rerun()

# -------------------------------------------------------------
# 7. SINGLE-SCREEN TRADING DESK WITH VISUAL SL/TP LINES
# -------------------------------------------------------------
st.markdown("### 🖥️ Single-Screen Trading Desk")
desk_left, desk_right = st.columns([2.3, 1.2])

with desk_left:
    sel_c1, sel_c2 = st.columns([2, 1])
    with sel_c1:
        active_chart_asset = st.selectbox("Active Asset:", tickers_in_univ, index=0, key="screen_asset_sel")
    with sel_c2:
        chart_interval_desk = st.selectbox("Desk TF:", ["5m", "15m", "60m", "D"], index=2, key="chart_tf_sel")
        
    active_ticker = resolve_ticker(active_chart_asset)
    df_chart = fetch_chart_dataframe(active_ticker, chart_interval_desk)
    
    if not df_chart.empty:
        plot_df = df_chart.tail(65).copy()
        plot_df['EMA20'] = plot_df['Close'].ewm(span=20, adjust=False).mean()
        
        c_cur = float(plot_df['Close'].iloc[-1])
        atr_calc = float(ta.volatility.average_true_range(plot_df['High'], plot_df['Low'], plot_df['Close'], window=14).dropna().iloc[-1]) if len(plot_df) >= 15 else (c_cur * 0.01)

        open_match = next((t for t in open_trades if t.get("asset") == active_chart_asset), None)
        if open_match:
            chart_sl = float(open_match.get("sl"))
            chart_tp1 = float(open_match.get("tp1"))
            chart_tp2 = float(open_match.get("tp2"))
            chart_entry = float(open_match.get("entry"))
        else:
            chart_sl = c_cur - (1.0 * atr_calc)
            chart_tp1 = c_cur + (2.0 * atr_calc)
            chart_tp2 = c_cur + (3.5 * atr_calc)
            chart_entry = c_cur

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=plot_df.index,
            open=plot_df['Open'],
            high=plot_df['High'],
            low=plot_df['Low'],
            close=plot_df['Close'],
            name="Price",
            increasing_line_color='#089981',
            decreasing_line_color='#f23645',
            increasing_fillcolor='#089981',
            decreasing_fillcolor='#f23645',
            line=dict(width=1.5)
        ))

        fig.add_trace(go.Scatter(
            x=plot_df.index,
            y=plot_df['EMA20'],
            line=dict(color='#ff9800', width=1.5),
            name="EMA 20"
        ))

        # Visual Entry, SL & Target Reference Lines
        fig.add_hline(y=chart_tp1, line_dash="solid", line_color="#00e676", line_width=1.5,
                      annotation_text=f"TP 1 (1:2): {chart_tp1:.2f}", annotation_position="top right")
        fig.add_hline(y=chart_tp2, line_dash="dash", line_color="#00b0ff", line_width=1.5,
                      annotation_text=f"TP 2 (1:3.5): {chart_tp2:.2f}", annotation_position="top right")
        fig.add_hline(y=chart_entry, line_dash="dot", line_color="#ffffff", line_width=1.0,
                      annotation_text=f"Entry: {chart_entry:.2f}", annotation_position="bottom right")
        fig.add_hline(y=chart_sl, line_dash="dash", line_color="#ff1744", line_width=1.5,
                      annotation_text=f"SL: {chart_sl:.2f}", annotation_position="bottom right")

        fig.update_layout(
            template="plotly_dark",
            height=520,
            margin=dict(l=5, r=60, t=35, b=10),
            xaxis_rangeslider_visible=False,
            title=f"<b>{active_chart_asset}</b> ({active_ticker}) - Live Chart",
            paper_bgcolor="#131722",
            plot_bgcolor="#131722",
            yaxis=dict(side="right", gridcolor="#1e222d"),
            xaxis=dict(gridcolor="#1e222d", type="category")
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

    sl_dist = 1.0 * atr_val
    auto_sl_buy = round(asset_ltp - sl_dist, 4 if (is_fx and asset_ltp < 20) else 2)
    auto_tp_buy = round(asset_ltp + (2.0 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)
    auto_tp2_buy = round(asset_ltp + (3.5 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)

    st.metric(f"{active_chart_asset} Live Price", f"{curr_prefix}{dec_fmt % asset_ltp}")

    fast_qty = st.number_input("Lots / Qty:", min_value=1, value=2, step=1, help="Quantity must be >=2 for 50% partial exit")
    req_fund = asset_ltp * fast_qty

    col_sl_b, col_tp_b = st.columns(2)
    with col_sl_b:
        exec_sl = st.number_input("Auto SL (1x ATR):", value=float(auto_sl_buy), step=step_val, format=dec_fmt)
    with col_tp_b:
        exec_tp = st.number_input("Auto Target (1:2):", value=float(auto_tp_buy), step=step_val, format=dec_fmt)

    # ----------------- HIGH-VISIBILITY BALANCE WIDGET -----------------
    bal_col1, bal_col2 = st.columns(2)
    with bal_col1:
        st.markdown(f"""
        <div style="background-color: #1a1e29; padding: 6px 10px; border-radius: 6px; border: 1px solid #30363d;">
            <span style="font-size: 11px; color: #8b949e;">Order Margin</span><br>
            <b style="font-size: 14px; color: #ffb74d;">₹{req_fund:,.2f}</b>
        </div>
        """, unsafe_allow_html=True)
    with bal_col2:
        st.markdown(f"""
        <div style="background-color: #1a1e29; padding: 6px 10px; border-radius: 6px; border: 1px solid #30363d;">
            <span style="font-size: 11px; color: #8b949e;">Available Funds</span><br>
            <b style="font-size: 14px; color: #4caf50;">₹{available_balance:,.2f}</b>
        </div>
        """, unsafe_allow_html=True)
    st.write("")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🟢 BUY (Mkt)", use_container_width=True):
            if req_fund > available_balance and available_balance > 0:
                st.warning(f"Low Balance Warning: Margin Req ₹{req_fund:,.2f} > Avail ₹{available_balance:,.2f}.")
            
            try:
                valid_ids = pd.to_numeric(sheet_trades_df["id"], errors="coerce").dropna()
                new_id = int(valid_ids.max() + 1) if not valid_ids.empty else 1
            except Exception:
                new_id = 1

            new_row = pd.DataFrame([{
                "id": new_id,
                "date": ist_now.strftime("%Y-%m-%d %H:%M"),
                "asset": active_chart_asset,
                "type": "BUY",
                "entry": float(asset_ltp),
                "sl": float(exec_sl),
                "tp1": float(exec_tp),
                "tp2": float(auto_tp2_buy),
                "qty": int(fast_qty),
                "invested_capital": float(req_fund),
                "status": "OPEN",
                "timeframe": chart_interval_desk,
                "exit_price": 0.0,
                "exit_time": "",
                "pnl": 0.0,
                "partial_booked": "NO"
            }])
            
            save_sheet_trades(pd.concat([sheet_trades_df, new_row], ignore_index=True))
            st.success(f"Buy Executed for {active_chart_asset} at {asset_ltp}!")
            st.rerun()

    with col_btn2:
        if st.button("🔴 SELL (Mkt)", use_container_width=True):
            if req_fund > available_balance and available_balance > 0:
                st.warning(f"Low Balance Warning: Margin Req ₹{req_fund:,.2f} > Avail ₹{available_balance:,.2f}.")

            try:
                valid_ids = pd.to_numeric(sheet_trades_df["id"], errors="coerce").dropna()
                new_id = int(valid_ids.max() + 1) if not valid_ids.empty else 1
            except Exception:
                new_id = 1

            auto_sl_sell = round(asset_ltp + sl_dist, 4 if (is_fx and asset_ltp < 20) else 2)
            auto_tp_sell = round(asset_ltp - (2.0 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)
            auto_tp2_sell = round(asset_ltp - (3.5 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)

            new_row = pd.DataFrame([{
                "id": new_id,
                "date": ist_now.strftime("%Y-%m-%d %H:%M"),
                "asset": active_chart_asset,
                "type": "SELL",
                "entry": float(asset_ltp),
                "sl": float(auto_sl_sell),
                "tp1": float(auto_tp_sell),
                "tp2": float(auto_tp2_sell),
                "qty": int(fast_qty),
                "invested_capital": float(req_fund),
                "status": "OPEN",
                "timeframe": chart_interval_desk,
                "exit_price": 0.0,
                "exit_time": "",
                "pnl": 0.0,
                "partial_booked": "NO"
            }])
            
            save_sheet_trades(pd.concat([sheet_trades_df, new_row], ignore_index=True))
            st.success(f"Sell Executed for {active_chart_asset} at {asset_ltp}!")
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
            st_text = tr.get("status")

            st.markdown(f"""
            <div style="background-color: #1a1e29; padding: 8px; border-radius: 5px; margin-bottom: 6px; border-left: 4px solid {pnl_c};">
                <div style="display:flex; justify-content:space-between;">
                    <b>{tr.get('asset')}</b>
                    <span style="color:{pnl_c}; font-weight:bold;">₹{live_pnl:+,.2f}</span>
                </div>
                <div style="font-size:11px; color:#90caf9;">Qty: {q_val} | Entry: {e_val:.2f} | Status: {st_text}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Exit Position #{idx+1}", key=f"fast_exit_{tr.get('id')}", use_container_width=True):
                idx_l = sheet_trades_df.index[sheet_trades_df["id"] == tr.get('id')].tolist()
                if idx_l:
                    sheet_trades_df.at[idx_l[0], "status"] = "MANUAL_EXIT"
                    sheet_trades_df.at[idx_l[0], "exit_price"] = c_val
                    sheet_trades_df.at[idx_l[0], "exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
                    sheet_trades_df.at[idx_l[0], "pnl"] = float(sheet_trades_df.at[idx_l[0], "pnl"] or 0.0) + live_pnl
                    save_sheet_trades(sheet_trades_df)
                    st.rerun()
    else:
        st.caption("No running positions right now.")

st.markdown("---")

# -------------------------------------------------------------
# 8. MULTI-TIMEFRAME CONFIRMATION SCREENER (15m + 1h SYNC)
# -------------------------------------------------------------
st.markdown(f"### 📋 {selected_universe} - Multi-Timeframe Synced Scanner (15m + 1h)")

@st.cache_data(ttl=90)
def scan_mtf_assets(asset_list):
    scan_rows = []
    for asset_name in asset_list:
        tick = resolve_ticker(asset_name)
        df_1h = fetch_chart_dataframe(tick, "60m")
        df_15m = fetch_chart_dataframe(tick, "15m")
        
        if df_1h.empty or len(df_1h) < 20 or df_15m.empty or len(df_15m) < 20:
            continue
        try:
            c_1h = float(df_1h['Close'].iloc[-1])
            ema20_1h = float(ta.trend.ema_indicator(df_1h['Close'], window=20).dropna().iloc[-1])
            trend_1h_bullish = c_1h > ema20_1h
            trend_1h_bearish = c_1h < ema20_1h

            c_15m = float(df_15m['Close'].iloc[-1])
            c_vol = float(df_15m['Volume'].iloc[-1])
            
            prev_20 = df_15m.iloc[-21:-1]
            res_level = float(prev_20['High'].max())
            sup_level = float(prev_20['Low'].min())
            avg_vol = float(prev_20['Volume'].mean()) or 1.0
            rvol = round(c_vol / avg_vol, 2) if avg_vol > 0 else 1.0

            atr_s = ta.volatility.average_true_range(df_15m['High'], df_15m['Low'], df_15m['Close'], window=14)
            atr = float(atr_s.dropna().iloc[-1]) if not atr_s.dropna().empty else (c_15m * 0.015)

            rsi_s = ta.momentum.rsi(df_15m['Close'], window=14)
            rsi = float(rsi_s.dropna().iloc[-1]) if not rsi_s.dropna().empty else 50.0

            ema20_15m = float(ta.trend.ema_indicator(df_15m['Close'], window=20).dropna().iloc[-1])

            is_buy = (trend_1h_bullish) and (c_15m > res_level) and (c_15m > ema20_15m) and (50 <= rsi <= 68)
            is_sell = (trend_1h_bearish) and (c_15m < sup_level) and (c_15m < ema20_15m) and (32 <= rsi <= 50)
            divergence_warn = (c_15m > res_level and not trend_1h_bullish) or (c_15m < sup_level and not trend_1h_bearish)

            is_special = any(sp in tick for sp in ["=X", "=F", "-USD"]) or ("/" in asset_name)
            dec = 4 if (is_special and c_15m < 20) else 2

            sl_dist = 1.0 * atr

            if is_buy:
                status_str = "🟢 BUY BREAKOUT (MTF SYNCED)"
                sl_calc = c_15m - sl_dist
                tp1_calc = c_15m + (2.0 * sl_dist)
            elif is_sell:
                status_str = "🔴 SELL BREAKDOWN (MTF SYNCED)"
                sl_calc = c_15m + sl_dist
                tp1_calc = c_15m - (2.0 * sl_dist)
            elif divergence_warn:
                status_str = "⚠️ FALSE BREAKOUT FILTERED"
                sl_calc = c_15m - sl_dist
                tp1_calc = c_15m + (2.0 * sl_dist)
            else:
                status_str = "⚪ NEUTRAL"
                sl_calc = c_15m - sl_dist
                tp1_calc = c_15m + (2.0 * sl_dist)

            scan_rows.append({
                "Asset": asset_name,
                "Signal Status": status_str,
                "LTP": round(c_15m, dec),
                "1h Trend": "Bullish 🐂" if trend_1h_bullish else "Bearish 🐻",
                "Stop Loss": round(sl_calc, dec),
                "Target 1 (1:2)": round(tp1_calc, dec),
                "RSI (15m)": round(rsi, 1),
                "RVol": "Liquid" if is_special else f"{rvol}x"
            })
        except Exception:
            continue
    return pd.DataFrame(scan_rows)

screener_df = scan_mtf_assets(tickers_in_univ)

if not screener_df.empty:
    filter_col1, filter_col2 = st.columns([1.5, 3])
    with filter_col1:
        status_filter = st.selectbox("Filter Confluence:", ["All", "🟢 BUY BREAKOUT (MTF SYNCED)", "🔴 SELL BREAKDOWN (MTF SYNCED)", "⚠️ FALSE BREAKOUT FILTERED", "⚪ NEUTRAL"], index=0)
    
    filtered_view = screener_df.copy()
    if status_filter != "All":
        filtered_view = filtered_view[filtered_view["Signal Status"] == status_filter]
        
    st.dataframe(filtered_view, use_container_width=True, hide_index=True)
else:
    st.info("Scanning Multi-Timeframe Feeds... Please allow a few seconds.")
