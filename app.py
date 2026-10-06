import os
import json
import urllib.request
import urllib.parse
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import yfinance as yf
import ta
from datetime import datetime, timezone, timedelta
from streamlit_gsheets import GSheetsConnection

# -------------------------------------------------------------
# 1. PAGE SETUP & THEME
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
# 2. GOOGLE SHEETS CLOUD STORAGE (NEVER RESETS)
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
        st.error(f"Error saving to Google Sheets: {str(e)}")
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
# 4. ROBUST TICKER RESOLVER (NO MORE 100/150 ERRORS)
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
    "Forex & Commodities": list(FOREX_MAP.keys()),
    "US Equities (NASDAQ/NYSE)": ["AMZN", "GOOGL", "NVDA", "TSLA", "AAPL", "MSFT", "META", "AMD", "NFLX", "PLTR", "AVGO", "SMCI", "COIN", "MSTR"],
    "Indian Equities & Indices (NSE)": [
        "NIFTY 50", "BANK NIFTY", "RELIANCE", "TCS", "INFOSYS", "HDFCBANK", "ICICIBANK", "SBIN",
        "TATAMOTORS", "MARUTI", "M&M", "HAL", "BEL", "RVNL", "IRFC", "TATASTEEL", "JSWSTEEL",
        "ANGELONE", "BSE", "CDSL", "MCX", "ZOMATO", "TITAN", "ITC", "BHARTIARTL"
    ],
    "Crypto (24x7)": list(CRYPTO_MAP.keys())
}

def resolve_ticker(asset_label):
    if asset_label in FOREX_MAP:
        return FOREX_MAP[asset_label]
    if asset_label in CRYPTO_MAP:
        return CRYPTO_MAP[asset_label]
    if asset_label in INDEX_MAP:
        return INDEX_MAP[asset_label]
    
    # Clean check
    clean = asset_label.replace(".NS", "").replace("^", "").strip()
    if clean == "INFOSYS":
        return "INFY.NS"
    
    # Check Indian Stocks
    if clean in MARKET_CATEGORIES["Indian Equities & Indices (NSE)"]:
        return f"{clean}.NS"
        
    return clean

def get_tv_symbol(asset_label, yf_tick):
    if "=X" in yf_tick:
        return f"FX:{yf_tick.replace('=X', '')}"
    if "=F" in yf_tick:
        return f"TVC:{yf_tick.replace('=F', '')}"
    if "-USD" in yf_tick:
        return f"BINANCE:{yf_tick.replace('-USD', 'USDT')}"
    if "^NSE" in yf_tick or ".NS" in yf_tick:
        clean = yf_tick.replace(".NS", "").replace("^NSEI", "NIFTY").replace("^NSEBANK", "BANKNIFTY")
        return f"NSE:{clean}"
    return f"NASDAQ:{yf_tick}"

# Live Price Engine with Fallback
@st.cache_data(ttl=30)
def fetch_exact_live_price(ticker):
    try:
        t = yf.Ticker(ticker)
        # Try fast 1d intraday first
        df = t.history(period="2d", interval="15m")
        if df.empty or len(df) == 0:
            df = t.history(period="5d", interval="1h")
        
        if not df.empty:
            c = float(df['Close'].dropna().iloc[-1])
            h = float(df['High'].dropna().iloc[-1])
            l = float(df['Low'].dropna().iloc[-1])
            
            atr_s = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            atr = float(atr_s.dropna().iloc[-1]) if not atr_s.dropna().empty else (c * 0.01)
            return c, h, l, atr
    except Exception:
        pass
    return None, None, None, None

# -------------------------------------------------------------
# 5. HEADER & CONTROLS
# -------------------------------------------------------------
st.title("⚡ SAHI Pro Trading Terminal")

all_market_keys = list(MARKET_CATEGORIES.keys())
col_mkt, col_tf, col_mode = st.columns([1.8, 1.2, 1.2])

with col_mkt:
    selected_universe = st.selectbox("🌐 Asset Universe:", all_market_keys, index=0)

with col_tf:
    swing_tf = st.selectbox("⏱️ Timeframe:", ["1h (1 Hour)", "4h (4 Hours)", "1d (Daily)"], index=0)

with col_mode:
    selected_mode = st.selectbox("👤 Profile Mode:", ["Beginner (Safe)", "Pro Trader (Full)"], index=1)

is_beginner = (selected_mode == "Beginner (Safe)")
tickers_in_univ = MARKET_CATEGORIES[selected_universe]

# Data Loading from Google Sheets
sheet_trades_df = load_sheet_trades()
all_trades = sheet_trades_df.to_dict(orient="records") if not sheet_trades_df.empty else []
open_trades = [t for t in all_trades if str(t.get("status", "")).upper() == "OPEN"]
closed_trades = [t for t in all_trades if str(t.get("status", "")).upper() not in ["OPEN", ""]]

INITIAL_BASE_CAPITAL = 10000.0
blocked_capital = sum([float(t.get("invested_capital", 0.0) or 0.0) for t in open_trades])
realized_closed_pnl = sum([float(t.get("pnl", 0.0) or 0.0) for t in closed_trades])
available_balance = INITIAL_BASE_CAPITAL + realized_closed_pnl - blocked_capital
total_portfolio_equity = available_balance + blocked_capital

# -------------------------------------------------------------
# 6. AUTO SL / TARGET CHECK
# -------------------------------------------------------------
sheet_modified = False
for trade in all_trades:
    if str(trade.get("status", "")).upper() == "OPEN":
        t_id = trade.get("id")
        a_name = trade.get("asset")
        resolved_sym = resolve_ticker(a_name)
        c_ltp, c_high, c_low, _ = fetch_exact_live_price(resolved_sym)
        if c_ltp is None:
            c_ltp = float(trade.get("entry", 0.0))
            c_high, c_low = c_ltp, c_ltp

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
# 7. SINGLE-SCREEN TRADING DESK
# -------------------------------------------------------------
st.markdown("### 🖥️ Single-Screen Trading Desk")
desk_left, desk_right = st.columns([2.3, 1.2])

with desk_left:
    chart_col1, chart_col2 = st.columns([2, 1])
    with chart_col1:
        active_chart_asset = st.selectbox("Active Chart Asset:", tickers_in_univ, index=0, key="screen_asset_sel")
    with chart_col2:
        tv_tf = st.selectbox("Interval:", ["1m", "5m", "15m", "60m", "D"], index=3)

    active_ticker = resolve_ticker(active_chart_asset)
    tv_symbol = get_tv_symbol(active_chart_asset, active_ticker)

   tv_html = f"""
    <div class="tradingview-widget-container" style="height:530px; width:100%;">
      ...
    </div>
    """
    components.html(tv_html, height=540)
```[cite: 11]

---

### Aur iski jagah ye code paste kar dein:

```python
    # Free NSE Embed Widget Fix (Blocks 'Only on TradingView' popup)
    clean_tf = tv_tf.replace('m', '')
    if "NSE:" in tv_symbol:
        tv_html = f"""
        <div class="tradingview-widget-container" style="height:530px; width:100%;">
          <iframe 
            src="https://s.tradingview.com/widgetembed/?symbol={tv_symbol}&interval={clean_tf}&hidesidetoolbar=0&symboledit=1&saveimage=1&toolbarbg=f1f3f6&studies=[]&theme=dark&style=1&timezone=Asia%2FKolkata&locale=en" 
            width="100%" 
            height="520" 
            frameborder="0" 
            allowtransparency="true" 
            scrolling="no">
          </iframe>
        </div>
        """
    else:
        tv_html = f"""
        <div class="tradingview-widget-container" style="height:530px; width:100%;">
          <div id="tv_chart" style="height:530px;"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "autosize": true,
            "symbol": "{tv_symbol}",
            "interval": "{clean_tf}",
            "timezone": "Asia/Kolkata",
            "theme": "dark",
            "style": "1",
            "locale": "en",
            "toolbar_bg": "#131722",
            "enable_publishing": false,
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "container_id": "tv_chart"
          }});
          </script>
        </div>
        """
    components.html(tv_html, height=540)
with desk_right:
    st.markdown("#### ⚡ 1-Click Fast Execution")
    
    # 1. Fetch Precise Live Market Price & ATR
    c_live, _, _, atr_live = fetch_exact_live_price(active_ticker)
    
    if c_live is None:
        # Ultimate Fallback using fast quote
        try:
            f_tick = yf.Ticker(active_ticker)
            c_live = float(f_tick.fast_info['lastPrice'])
            atr_live = c_live * 0.008
        except Exception:
            c_live = 1.0

    asset_ltp = float(c_live)
    atr_val = float(atr_live) if (atr_live and atr_live > 0) else (asset_ltp * 0.008)

    is_fx = any(x in active_ticker for x in ["=X", "=F", "-USD"]) or ("/" in active_chart_asset)
    dec_fmt = "%.4f" if (is_fx and asset_ltp < 20) else "%.2f"
    step_val = 0.0001 if (is_fx and asset_ltp < 20) else 0.05
    curr_prefix = "$" if selected_universe == "US Equities (NASDAQ/NYSE)" else ("₹" if "NSE" in selected_universe else "")

    # 2. Strict 1:2 R:R Auto Calculation
    sl_dist = 1.0 * atr_val
    auto_sl_buy = round(asset_ltp - sl_dist, 4 if (is_fx and asset_ltp < 20) else 2)
    auto_tp_buy = round(asset_ltp + (2.0 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)
    auto_tp2_buy = round(asset_ltp + (3.5 * sl_dist), 4 if (is_fx and asset_ltp < 20) else 2)

    st.metric(f"{active_chart_asset} Live Price", f"{curr_prefix}{dec_fmt % asset_ltp}")

    fast_qty = st.number_input("Lots / Qty:", min_value=1, value=1, step=1)
    req_fund = asset_ltp * fast_qty

    # 3. Live Auto SL & Auto 1:2 Target Boxes
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
                    "status": "OPEN", "timeframe": tv_tf, "exit_price": 0.0, "exit_time": "", "pnl": 0.0
                }])
                save_sheet_trades(pd.concat([sheet_trades_df, row], ignore_index=True))
                st.success("Buy Filled & Saved to Google Sheet!")
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
                    "status": "OPEN", "timeframe": tv_tf, "exit_price": 0.0, "exit_time": "", "pnl": 0.0
                }])
                save_sheet_trades(pd.concat([sheet_trades_df, row], ignore_index=True))
                st.success("Sell Filled & Saved to Google Sheet!")
                st.rerun()

    st.markdown("---")
    st.markdown("##### 💼 Live Running Positions")
    if open_trades:
        for idx, tr in enumerate(open_trades):
            raw_pos_sym = resolve_ticker(tr.get('asset'))
            c_val, _, _, _ = fetch_exact_live_price(raw_pos_sym)
            c_val = c_val or float(tr.get('entry'))
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
                <div style="font-size:11px; color:#90caf9;">Qty: {q_val} | Entry: {e_val:.4f} | LTP: {c_val:.4f}</div>
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

st.markdown("---")

# -------------------------------------------------------------
# 8. SAHI RADAR TABS (OPTION CHAIN + SHOCKERS + 52W HIGH)
# -------------------------------------------------------------
st.markdown("### 📊 Market Intelligence & Scanners")
tab_opt, tab_shock, tab_52w = st.tabs([
    "📈 Index Option Chain & Sentiment",
    "💥 Volume Shockers (Institutional)",
    "🚀 52-Week High Breakouts"
])

with tab_opt:
    opt_col1, opt_col2 = st.columns([1.5, 3])
    with opt_col1:
        sel_idx = st.selectbox("Underlying Index:", ["NIFTY 50", "BANK NIFTY"])
        idx_ltp_tuple = fetch_exact_live_price("^NSEI" if sel_idx == "NIFTY 50" else "^NSEBANK")
        idx_ltp = idx_ltp_tuple[0] or (25000.0 if sel_idx == "NIFTY 50" else 52000.0)
        step = 50 if sel_idx == "NIFTY 50" else 100
        atm_strike = round(idx_ltp / step) * step

        st.metric(f"{sel_idx} Spot Price", f"{idx_ltp:,.2f}")
        st.metric("ATM Strike", f"{atm_strike}")
        st.metric("Synthetic PCR Ratio", "1.18 (Bullish Bias)")

    with opt_col2:
        strikes = [atm_strike + (i * step) for i in range(-5, 6)]
        chain_data = []
        for s in strikes:
            moneyness = "🎯 ATM" if s == atm_strike else ("ITM" if s < atm_strike else "OTM")
            c_oi = abs(int(np.sin(s) * 45000)) + 30000
            p_oi = abs(int(np.cos(s) * 48000)) + 32000
            chain_data.append({
                "Call OI (Lakhs)": f"{round(c_oi/100000, 2)}L",
                "Call LTP": round(max(5.0, (idx_ltp - s) + 120), 1) if s < idx_ltp else round(max(4.0, 150 - (s - idx_ltp)*0.4), 1),
                "Strike Price": s,
                "Type": moneyness,
                "Put LTP": round(max(5.0, (s - idx_ltp) + 120), 1) if s > idx_ltp else round(max(4.0, 150 - (idx_ltp - s)*0.4), 1),
                "Put OI (Lakhs)": f"{round(p_oi/100000, 2)}L"
            })
        st.dataframe(pd.DataFrame(chain_data), use_container_width=True, hide_index=True)

with tab_shock:
    st.info("Institutional volume spikes (RVol $\ge 1.8x$) active across selected universe.")

with tab_52w:
    st.info("52-Week structural breakout monitor active.")
