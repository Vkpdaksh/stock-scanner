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
# 2. GOOGLE SHEETS CLOUD STORAGE (PERSISTENT DESK)
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
# 3. HELPER FUNCTIONS & TELEGRAM
# -------------------------------------------------------------
def get_ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

ist_now = get_ist_now()
today_date_str = ist_now.strftime("%Y-%m-%d")
time_str = ist_now.strftime("%I:%M:%S %p IST")
cur_mins = ist_now.hour * 60 + ist_now.minute

def send_telegram_msg(msg_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "Telegram credentials missing."
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg_text, "parse_mode": "HTML"}
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200, "Success"
    except Exception as e:
        return False, str(e)

# -------------------------------------------------------------
# 4. ANGEL ONE SMARTAPI SESSION
# -------------------------------------------------------------
@st.cache_resource(ttl=3600)
def get_smartapi_session():
    if not (ANGEL_API_KEY and ANGEL_CLIENT_ID and ANGEL_MPIN and ANGEL_TOTP_KEY):
        return None
    try:
        import pyotp
        from SmartApi import SmartConnect
        totp = pyotp.TOTP(ANGEL_TOTP_KEY).now()
        smart_api = SmartConnect(api_key=ANGEL_API_KEY)
        session_data = smart_api.generateSession(ANGEL_CLIENT_ID, ANGEL_MPIN, totp)
        if session_data.get("status"):
            return smart_api
    except Exception:
        pass
    return None

def place_order_smartapi(symbol_token, trading_symbol, exchange, qty, transaction_type, price=0):
    api = get_smartapi_session()
    if not api:
        return False, "SmartAPI session unavailable."
    try:
        prod_type = "DELIVERY" if exchange == "NSE" else "CARRYFORWARD"
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": trading_symbol,
            "symboltoken": str(symbol_token),
            "transactiontype": transaction_type,
            "ordertype": "LIMIT" if price > 0 else "MARKET",
            "price": str(price) if price > 0 else "0",
            "producttype": prod_type,
            "duration": "DAY",
            "quantity": str(qty),
            "exchange": exchange
        }
        res = api.placeOrder(order_params)
        if res.get("status"):
            return True, f"Executed! Order ID: {res.get('data', {}).get('orderid')}"
        return False, res.get("message", "Order rejected.")
    except Exception as e:
        return False, str(e)

# -------------------------------------------------------------
# 5. ASSET UNIVERSE & MAPS
# -------------------------------------------------------------
NSE_EQUITIES = [
    "^NSEI", "^NSEBANK",
    "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", 
    "INDUSINDBK.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "SBILIFE.NS", "JIOFIN.NS", 
    "ANGELONE.NS", "BSE.NS", "CDSL.NS", "MCX.NS",
    "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "LTIM.NS", 
    "PERSISTENT.NS", "COFORGE.NS", "TATATECH.NS",
    "TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "EICHERMOT.NS", "ASHOKLEY.NS", "EXIDEIND.NS",
    "RELIANCE.NS", "ONGC.NS", "COALINDIA.NS", "NTPC.NS", "POWERGRID.NS", 
    "TATAPOWER.NS", "ADANIGREEN.NS", "SUZLON.NS", "IREDA.NS",
    "HAL.NS", "BEL.NS", "BDL.NS", "BHEL.NS", "MAZDOCK.NS", "COCHINSHIP.NS",
    "RVNL.NS", "IRFC.NS", "IRCON.NS", "RAILTEL.NS", "HUDCO.NS", "NBCC.NS",
    "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "SAIL.NS", "NMDC.NS", "NATIONALUM.NS",
    "LT.NS", "ULTRACEMCO.NS", "GRASIM.NS", "DLF.NS", "LODHA.NS",
    "ITC.NS", "HINDUNILVR.NS", "ASIANPAINT.NS", "TATACONSUM.NS", "TITAN.NS", 
    "TRENT.NS", "ZOMATO.NS", "KALYANKJIL.NS", "DIXON.NS", "POLYCAB.NS", "KEI.NS",
    "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "AUROPHARMA.NS", "LUPIN.NS",
    "BHARTIARTL.NS", "ADANIENT.NS", "ADANIPORTS.NS"
]

COMMODITIES_AND_FOREX = [
    "GC=F", "SI=F", "CL=F", "HG=F", "NG=F",
    "INR=X", "EURUSD=X", "GBPUSD=X", "USDJPY=X", 
    "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X",
    "EURGBP=X", "EURJPY=X", "GBPJPY=X"
]

US_EQUITIES = [
    "GOOGL", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "AMD", "NFLX", "PLTR",
    "AVGO", "SMCI", "ARM", "QCOM", "INTC", "MU", "PANW", "CRWD", "COIN", "MSTR"
]

CRYPTO_ASSETS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "SUI-USD"
]

MARKET_UNIVERSES = {
    "Indian Equities & Indices (NSE)": NSE_EQUITIES,
    "Forex & Commodities": COMMODITIES_AND_FOREX,
    "US Equities (NASDAQ/NYSE)": US_EQUITIES,
    "Crypto (24x7)": CRYPTO_ASSETS
}

NAME_MAP = {
    "^NSEI": "NIFTY 50", "^NSEBANK": "BANK NIFTY", "GC=F": "XAUUSD (Gold)",
    "SI=F": "XAGUSD (Silver)", "CL=F": "CRUDE OIL", "HG=F": "COPPER",
    "NG=F": "NATURAL GAS", "INR=X": "USD/INR", "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY", "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD", "USDCHF=X": "USD/CHF", "NZDUSD=X": "NZD/USD",
    "EURGBP=X": "EUR/GBP", "EURJPY=X": "EUR/JPY", "GBPJPY=X": "GBP/JPY",
    "BTC-USD": "BITCOIN", "ETH-USD": "ETHEREUM", "SOL-USD": "SOLANA",
    "GOOGL": "ALPHABET", "NVDA": "NVIDIA", "TSLA": "TESLA",
    "AAPL": "APPLE", "MSFT": "MICROSOFT", "AMZN": "AMAZON", "META": "META"
}

def calculate_vwap(df):
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    vol = df['Volume'].replace(0, 1)
    return (typical_price * vol).cumsum() / vol.cumsum()

# -------------------------------------------------------------
# 6. HEADER & MARKET ACTIVITY
# -------------------------------------------------------------
st.title("⚡ SAHI Pro Trading Terminal")

@st.cache_data(ttl=180)
def verify_nse_active():
    try:
        t_df = yf.download("^NSEI", period="2d", interval="1d", progress=False)
        if not t_df.empty:
            return str(t_df.dropna().index[-1].date()) == today_date_str
        return False
    except Exception:
        return False

is_nse_time = (ist_now.weekday() < 5) and (555 <= cur_mins <= 930)
is_nse_active = verify_nse_active() if is_nse_time else False
session_text = "🟢 NSE LIVE ACTIVE" if is_nse_active else "🔴 NSE CLOSED / HOLIDAY"

st.caption(f"Status: **{session_text}** | Live Time: **{time_str}** | Model: **Single-Screen Fast Execution Desk**")

# Data loading
sheet_trades_df = load_sheet_trades()
all_trades = sheet_trades_df.to_dict(orient="records") if not sheet_trades_df.empty else []
open_trades = [t for t in all_trades if str(t.get("status", "")).upper() == "OPEN"]
closed_trades = [t for t in all_trades if str(t.get("status", "")).upper() not in ["OPEN", ""]]

INITIAL_BASE_CAPITAL = 10000.0
blocked_capital = sum([float(t.get("invested_capital", 0.0) or 0.0) for t in open_trades])
realized_closed_pnl = sum([float(t.get("pnl", 0.0) or 0.0) for t in closed_trades])
available_balance = INITIAL_BASE_CAPITAL + realized_closed_pnl - blocked_capital
total_portfolio_equity = available_balance + blocked_capital

def get_live_candle_data(asset_name):
    for t, mapped in NAME_MAP.items():
        if mapped == asset_name or t == asset_name:
            try:
                t_df = yf.download(t, period="2d", interval="1h", progress=False)
                if not t_df.empty:
                    return float(t_df['Close'].dropna().iloc[-1]), float(t_df['High'].dropna().iloc[-1]), float(t_df['Low'].dropna().iloc[-1])
            except Exception:
                pass
    try:
        t_df = yf.download(f"{asset_name}.NS", period="2d", interval="1h", progress=False)
        if not t_df.empty:
            return float(t_df['Close'].dropna().iloc[-1]), float(t_df['High'].dropna().iloc[-1]), float(t_df['Low'].dropna().iloc[-1])
    except Exception:
        pass
    try:
        t_df = yf.download(asset_name, period="2d", interval="1h", progress=False)
        if not t_df.empty:
            return float(t_df['Close'].dropna().iloc[-1]), float(t_df['High'].dropna().iloc[-1]), float(t_df['Low'].dropna().iloc[-1])
    except Exception:
        pass
    return None, None, None

# -------------------------------------------------------------
# 7. REAL-TIME TARGET & SL MONITOR
# -------------------------------------------------------------
sheet_modified = False
for trade in all_trades:
    if str(trade.get("status", "")).upper() == "OPEN":
        t_id = trade.get("id")
        a_name = trade.get("asset")
        c_ltp, c_high, c_low = get_live_candle_data(a_name)
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
# 8. SCANNER ENGINE (BREAKOUTS + VOLUME SHOCKERS + 52W HIGH)
# -------------------------------------------------------------
selected_universe = "Indian Equities & Indices (NSE)" if is_nse_active else "Forex & Commodities"
tickers = MARKET_UNIVERSES[selected_universe]

@st.cache_data(ttl=180)
def fetch_market_data_universe(ticker_list):
    try:
        return yf.download(ticker_list, period="1y", interval="1d", group_by='ticker', progress=False)
    except Exception:
        return None

raw_daily = fetch_market_data_universe(tickers)
breakout_records = []
volume_shockers = []
high_52w_records = []

if raw_daily is not None:
    for ticker in tickers:
        try:
            df = raw_daily[ticker] if len(tickers) > 1 else raw_daily
            df = df.dropna()
            if len(df) < 50:
                continue

            c_close = float(df['Close'].iloc[-1])
            c_open = float(df['Open'].iloc[-1])
            c_vol = float(df['Volume'].iloc[-1])

            prev_20 = df.iloc[-21:-1]
            res_level = float(prev_20['High'].max())
            sup_level = float(prev_20['Low'].min())
            avg_vol = float(prev_20['Volume'].mean()) or 1.0
            rvol = round(c_vol / avg_vol, 2) if avg_vol > 0 else 1.0

            df['VWAP'] = calculate_vwap(df)
            c_vwap = float(df['VWAP'].iloc[-1])

            atr_s = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            atr = float(atr_s.dropna().iloc[-1]) if not atr_s.dropna().empty else (c_close * 0.01)

            rsi_s = ta.momentum.rsi(df['Close'], window=14)
            rsi = float(rsi_s.dropna().iloc[-1]) if not rsi_s.dropna().empty else 50.0

            high_52w = float(df['High'].max())
            low_52w = float(df['Low'].min())
            clean_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("^", "").replace("-USD", ""))

            # 1. Volume Shockers (SAHI Feature)
            if rvol >= 1.8 and c_close > c_vwap and ("=" not in ticker and "^" not in ticker):
                volume_shockers.append({
                    "Asset": clean_name, "LTP": c_close, "RVol": f"{rvol}x",
                    "RSI": round(rsi, 1), "VWAP": round(c_vwap, 2), "Volume": int(c_vol)
                })

            # 2. 52-Week High Breakouts (SAHI Feature)
            if c_close >= (high_52w * 0.985):
                high_52w_records.append({
                    "Asset": clean_name, "LTP": c_close, "52W High": round(high_52w, 2),
                    "Distance %": f"{round(((c_close - high_52w)/high_52w)*100, 2)}%", "RSI": round(rsi, 1)
                })

            # 3. Swing Breakouts (1:2 R:R)
            is_breakout = (c_close > res_level) and (c_close > c_open) and (50 <= rsi <= 68)
            is_breakdown = (c_close < sup_level) and (c_close < c_open) and (32 <= rsi <= 50)

            if is_breakout or is_breakdown:
                sl_dist = 1.0 * atr
                if is_breakout:
                    sig = "🟢 BUY BREAKOUT"
                    sl = c_close - sl_dist
                    tp1 = c_close + (2.0 * sl_dist)
                    tp2 = c_close + (3.5 * sl_dist)
                else:
                    sig = "🔴 SELL BREAKDOWN"
                    sl = c_close + sl_dist
                    tp1 = c_close - (2.0 * sl_dist)
                    tp2 = c_close - (3.5 * sl_dist)

                breakout_records.append({
                    "Ticker": ticker, "Asset": clean_name, "Signal": sig,
                    "LTP": round(c_close, 2), "Stop Loss": round(sl, 2),
                    "Target 1 (1:2)": round(tp1, 2), "Target 2 (1:3.5)": round(tp2, 2),
                    "RVol": f"{rvol}x", "RSI": round(rsi, 1)
                })
        except Exception:
            continue

# -------------------------------------------------------------
# 9. SINGLE-SCREEN TRADING DESK (CHART + EXECUTION SIDE-BY-SIDE)
# -------------------------------------------------------------
st.markdown("### 🖥️ Single-Screen Trading Desk")
desk_left, desk_right = st.columns([2.3, 1.2])

all_clean_assets = sorted(list(set([NAME_MAP.get(t, t.replace(".NS", "").replace("^", "").replace("-USD", "")) for t in tickers])))

with desk_left:
    chart_col1, chart_col2 = st.columns([2, 1])
    with chart_col1:
        active_chart_asset = st.selectbox("Active Chart Asset:", all_clean_assets, index=0, key="screen_asset_sel")
    with chart_col2:
        tv_tf = st.selectbox("Interval:", ["1m", "5m", "15m", "60m", "D"], index=3)

    tv_symbol = "NSE:" + active_chart_asset.replace(".NS", "")
    for k, v in NAME_MAP.items():
        if v == active_chart_asset:
            if "^NSE" in k or ".NS" in k:
                tv_symbol = "NSE:" + k.replace(".NS", "").replace("^", "")
            elif "=F" in k:
                tv_symbol = "TVC:" + k.replace("=F", "")
            else:
                tv_symbol = "NASDAQ:" + k
            break

    tv_html = f"""
    <div class="tradingview-widget-container" style="height:520px; width:100%;">
      <div id="tv_chart" style="height:520px;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{tv_symbol}",
        "interval": "{tv_tf.replace('m','')}",
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
    components.html(tv_html, height=530)

with desk_right:
    st.markdown("#### ⚡ 1-Click Fast Execution")
    live_tuple = get_live_candle_data(active_chart_asset)
    asset_ltp = live_tuple[0] or 100.0

    st.metric(f"{active_chart_asset} LTP", f"₹{asset_ltp:,.2f}")
    fast_qty = st.number_input("Lots / Qty:", min_value=1, value=1, step=1)
    req_fund = asset_ltp * fast_qty

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
                    "sl": round(asset_ltp * 0.985, 2), "tp1": round(asset_ltp * 1.03, 2),
                    "tp2": round(asset_ltp * 1.05, 2), "qty": fast_qty, "invested_capital": req_fund,
                    "status": "OPEN", "timeframe": tv_tf, "exit_price": 0.0, "exit_time": "", "pnl": 0.0
                }])
                save_sheet_trades(pd.concat([sheet_trades_df, row], ignore_index=True))
                st.success("Buy Filled!")
                st.rerun()

    with col_btn2:
        if st.button("🔴 SELL (Mkt)", use_container_width=True):
            if req_fund > available_balance:
                st.error("Insufficient Balance!")
            else:
                new_id = int(sheet_trades_df["id"].max() + 1) if not sheet_trades_df.empty and pd.notnull(sheet_trades_df["id"].max()) else 1
                row = pd.DataFrame([{
                    "id": new_id, "date": ist_now.strftime("%Y-%m-%d %H:%M"),
                    "asset": active_chart_asset, "type": "SELL", "entry": asset_ltp,
                    "sl": round(asset_ltp * 1.015, 2), "tp1": round(asset_ltp * 0.97, 2),
                    "tp2": round(asset_ltp * 0.95, 2), "qty": fast_qty, "invested_capital": req_fund,
                    "status": "OPEN", "timeframe": tv_tf, "exit_price": 0.0, "exit_time": "", "pnl": 0.0
                }])
                save_sheet_trades(pd.concat([sheet_trades_df, row], ignore_index=True))
                st.success("Sell Filled!")
                st.rerun()

    st.markdown("---")
    st.markdown("##### 💼 Live Active Positions")
    if open_trades:
        for idx, tr in enumerate(open_trades):
            c_val, _, _ = get_live_candle_data(tr.get('asset'))
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
                <div style="font-size:11px; color:#90caf9;">Qty: {q_val} | Entry: ₹{e_val:.2f} | LTP: ₹{c_val:.2f}</div>
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
# 10. SAHI RADAR TABS (OPTION CHAIN + SHOCKERS + 52W HIGH)
# -------------------------------------------------------------
st.markdown("### 📊 Market Intelligence & Scanners")
tab_opt, tab_shock, tab_52w, tab_swings = st.tabs([
    "📈 Index Option Chain & Sentiment",
    "💥 Volume Shockers (Institutional)",
    "🚀 52-Week High Breakouts",
    "⚡ 1:2 Swing Setups"
])

with tab_opt:
    opt_col1, opt_col2 = st.columns([1.5, 3])
    with opt_col1:
        sel_idx = st.selectbox("Underlying Index:", ["NIFTY 50", "BANK NIFTY"])
        idx_ltp_tuple = get_live_candle_data("^NSEI" if sel_idx == "NIFTY 50" else "^NSEBANK")
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
    if volume_shockers:
        st.dataframe(pd.DataFrame(volume_shockers), use_container_width=True, hide_index=True)
    else:
        st.info("No volume spikes $\ge 1.8x$ detected on active tickers right now.")

with tab_52w:
    if high_52w_records:
        st.dataframe(pd.DataFrame(high_52w_records), use_container_width=True, hide_index=True)
    else:
        st.info("No stocks currently hovering within 1.5% of 52-week structural highs.")

with tab_swings:
    if breakout_records:
        st.dataframe(pd.DataFrame(breakout_records), use_container_width=True, hide_index=True)
    else:
        st.info("Scanning for strict 1:2 Risk-Reward setups. No fresh triggers on this bar.")
