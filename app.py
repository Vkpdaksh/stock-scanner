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
# 1. PAGE SETUP & CONFIG
# -------------------------------------------------------------
st.set_page_config(
    page_title="Institutional Swing Trading Terminal",
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
# 2. GOOGLE SHEETS CLOUD STORAGE ENGINE (NEVER RESETS)
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
        # Reads the first sheet (worksheet=0 / Portfolio)
        df = conn.read(ttl="0s")
        if df is None or df.empty:
            return pd.DataFrame(columns=SHEET_COLUMNS)
        for col in SHEET_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df.dropna(how="all")
    except Exception as e:
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

def send_telegram_msg(msg_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "Telegram credentials missing in secrets."
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg_text,
            "parse_mode": "HTML"
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                return True, "Success"
            return False, f"Telegram API Error: Status {response.status}"
    except Exception as e:
        return False, f"Error: {str(e)}"

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
        return False, "SmartAPI credentials missing or session uninitialized."
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
            return True, f"Real Swing Order Placed! Order ID: {res.get('data', {}).get('orderid')}"
        return False, res.get("message", "Order rejected by broker.")
    except Exception as e:
        return False, str(e)

# -------------------------------------------------------------
# 5. WATCHLISTS & ASSETS UNIVERSE (COMPLETE ORIGINAL LIST)
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
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "GC=F": "XAUUSD (Gold)",
    "SI=F": "XAGUSD (Silver)",
    "CL=F": "CRUDE OIL",
    "HG=F": "COPPER",
    "NG=F": "NATURAL GAS",
    "INR=X": "USD/INR",
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD",
    "USDCHF=X": "USD/CHF",
    "NZDUSD=X": "NZD/USD",
    "EURGBP=X": "EUR/GBP",
    "EURJPY=X": "EUR/JPY",
    "GBPJPY=X": "GBP/JPY",
    "BTC-USD": "BITCOIN",
    "ETH-USD": "ETHEREUM",
    "SOL-USD": "SOLANA",
    "GOOGL": "ALPHABET (GOOGLE)",
    "NVDA": "NVIDIA",
    "TSLA": "TESLA",
    "AAPL": "APPLE",
    "MSFT": "MICROSOFT",
    "AMZN": "AMAZON",
    "META": "META PLATFORMS"
}

def calculate_vwap(df):
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    vol = df['Volume'].replace(0, 1)
    return (typical_price * vol).cumsum() / vol.cumsum()

# -------------------------------------------------------------
# 6. HEADER & PROFILE SWITCHER
# -------------------------------------------------------------
st.title("⚡ Institutional Swing Trading Terminal")

ist_now = get_ist_now()
time_str = ist_now.strftime("%I:%M:%S %p IST")
today_date_str = ist_now.strftime("%Y-%m-%d")
cur_mins = ist_now.hour * 60 + ist_now.minute

col_mode, col_exec, col_tf = st.columns([1.5, 1.5, 1.2])

with col_mode:
    selected_mode = st.selectbox(
        "👤 Profile Mode:",
        ["Beginner (Safe)", "Pro Trader (Full)"],
        index=1
    )

is_beginner = (selected_mode == "Beginner (Safe)")

with col_exec:
    if is_beginner:
        st.selectbox("Execution Route:", ["Virtual Paper Trading (Locked)"], disabled=True)
        execution_type = "Paper Trading"
    else:
        selected_execution = st.selectbox(
            "Execution Route:",
            ["Dual Engine (Paper + SmartAPI)", "Virtual Paper Trading", "Real Fund (SmartAPI)"],
            index=0
        )
        execution_type = "Dual" if "Dual" in selected_execution else ("SmartAPI" if "SmartAPI" in selected_execution else "Paper Trading")

with col_tf:
    swing_tf = st.selectbox("⏱️ Swing Timeframe:", ["1h (1 Hour)", "4h (4 Hours)", "1d (Daily)"], index=0)

# Load persistent trades from Google Sheet
sheet_trades_df = load_sheet_trades()
all_trades = sheet_trades_df.to_dict(orient="records") if not sheet_trades_df.empty else []

open_trades = [t for t in all_trades if str(t.get("status", "")).upper() == "OPEN"]
closed_trades = [t for t in all_trades if str(t.get("status", "")).upper() not in ["OPEN", ""]]

# Dynamic Portfolio Balance Calculation from 1 Sheet
INITIAL_BASE_CAPITAL = 10000.0
blocked_capital = sum([float(t.get("invested_capital", 0.0) or 0.0) for t in open_trades])
realized_closed_pnl = sum([float(t.get("pnl", 0.0) or 0.0) for t in closed_trades])

available_balance = INITIAL_BASE_CAPITAL + realized_closed_pnl - blocked_capital
total_portfolio_equity = available_balance + blocked_capital

# -------------------------------------------------------------
# 7. CAPITAL SIZING & RISK ALLOCATION DESK
# -------------------------------------------------------------
st.markdown("### 🛡️ Risk Management & Capital Allocation Desk")
r_col1, r_col2, r_col3, r_col4 = st.columns(4)

with r_col1:
    account_capital = st.number_input("Base Portfolio Capital (₹):", min_value=1000, value=int(total_portfolio_equity), step=1000)

with r_col2:
    risk_pct_choice = st.selectbox("Max Risk Per Trade (%):", [1.0, 1.5, 2.0, 3.0], index=0)

safe_budget = (account_capital * risk_pct_choice) / 100.0

with r_col3:
    risk_per_trade = st.number_input("Risk Per Position (₹):", min_value=50.0, value=float(safe_budget), step=25.0)

with r_col4:
    max_portfolio_risk = st.number_input("Max Portfolio Risk Cap (₹):", min_value=100.0, value=float(safe_budget * 4), step=50.0)

actual_risk_pct = (risk_per_trade / account_capital) * 100 if account_capital > 0 else 0

if actual_risk_pct > 2.0:
    st.error(f"🚨 **High Risk Alert:** Selected risk is **{actual_risk_pct:.1f}%**! Recommended safe risk: 1% - 2% (₹{safe_budget:.0f}).")
else:
    st.success(f"✅ **Disciplined Swing Risk:** Max risk per trade: ₹{risk_per_trade:.0f} | Target R:R: **1:2 (Institutional)**")

st.markdown("---")

# -------------------------------------------------------------
# 8. ABSOLUTE ZERO-GAP HOLIDAY & HEARTBEAT ENGINE
# -------------------------------------------------------------
@st.cache_data(ttl=180)
def verify_market_trading_today(benchmark_symbol):
    try:
        test_df = yf.download(benchmark_symbol, period="2d", interval="1d", progress=False)
        if not test_df.empty:
            last_date = str(test_df.dropna().index[-1].date())
            return (last_date == today_date_str)
        return False
    except Exception:
        return False

is_weekday = ist_now.weekday() < 5
is_nse_hours = is_weekday and (555 <= cur_mins <= 930)

if is_nse_hours:
    is_nse_active = verify_market_trading_today("^NSEI")
else:
    is_nse_active = False

session_text = "🟢 NSE LIVE TRADING" if is_nse_active else "🔴 NSE CLOSED / MARKET HOLIDAY"
st.caption(f"Status: **{session_text}** | Live Time: **{time_str}** | Storage: **Google Sheets (Zero Reset)**")

# -------------------------------------------------------------
# 9. MARKET SCANNER ENGINE
# -------------------------------------------------------------
available_universes = list(MARKET_UNIVERSES.keys())

if is_nse_active:
    default_univ_index = available_universes.index("Indian Equities & Indices (NSE)")
elif 930 < cur_mins <= 1290:
    default_univ_index = available_universes.index("Forex & Commodities")
else:
    default_univ_index = available_universes.index("US Equities (NASDAQ/NYSE)")

selected_universe = st.selectbox("Active Asset Universe:", available_universes, index=default_univ_index)
tickers = MARKET_UNIVERSES[selected_universe]

tf_map = {
    "1h (1 Hour)": {"interval": "1h", "period": "1mo", "tv": "60"},
    "4h (4 Hours)": {"interval": "1h", "period": "3mo", "tv": "240"},
    "1d (Daily)": {"interval": "1d", "period": "6mo", "tv": "D"}
}
curr_tf_conf = tf_map[swing_tf]

@st.cache_data(ttl=180)
def fetch_market_data_shielded(ticker_list, interval, period):
    try:
        return yf.download(ticker_list, period=period, interval=interval, group_by='ticker', progress=False)
    except Exception:
        return None

raw_data = fetch_market_data_shielded(tickers, curr_tf_conf["interval"], curr_tf_conf["period"]) if tickers else None
records = []
active_breakouts = 0

if raw_data is not None:
    for ticker in tickers:
        try:
            df = raw_data[ticker] if len(tickers) > 1 else raw_data
            df = df.dropna()

            if "4h" in swing_tf and len(df) >= 8:
                df = df.resample('4h').agg({
                    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
                }).dropna()

            if len(df) < 20:
                continue

            is_indian_asset = (".NS" in ticker or "^NSE" in ticker)
            if is_indian_asset and not is_nse_active:
                continue

            candle_date_str = str(df.index[-1].date())
            if is_indian_asset and candle_date_str != today_date_str:
                continue

            c_close = float(df['Close'].iloc[-1])
            c_open = float(df['Open'].iloc[-1])
            c_vol = float(df['Volume'].iloc[-1])

            df['VWAP'] = calculate_vwap(df)
            c_vwap = float(df['VWAP'].iloc[-1])

            prev_window = df.iloc[-20:-1]
            res_level = float(prev_window['High'].max())
            sup_level = float(prev_window['Low'].min())
            avg_vol = float(prev_window['Volume'].mean()) or 1.0

            atr_s = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            atr = float(atr_s.dropna().iloc[-1]) if not atr_s.dropna().empty else (c_close * 0.01)

            rsi_s = ta.momentum.rsi(df['Close'], window=14)
            rsi = float(rsi_s.dropna().iloc[-1]) if not rsi_s.dropna().empty else 50.0

            ema20 = float(ta.trend.ema_indicator(df['Close'], window=20).dropna().iloc[-1])
            ema50 = float(ta.trend.ema_indicator(df['Close'], window=50).dropna().iloc[-1])

            is_special = ("=" in ticker or "^" in ticker or "-USD" in ticker)
            rvol = (c_vol / avg_vol) if avg_vol > 0 else 1.0
            rvol_display = "Liquid" if is_special else f"{round(rvol, 2)}x"

            is_breakout = (c_close > res_level) and (c_close > c_open) and (c_close > ema20) and (50 <= rsi <= 68)
            is_breakdown = (c_close < sup_level) and (c_close < c_open) and (c_close < ema20) and (32 <= rsi <= 50)

            if is_breakout:
                signal = "🟢 SWING BUY BREAKOUT"
                active_breakouts += 1
                trade_logic = f"Fresh breakout above {res_level:.2f} | 1:2 R:R Target Set."
                grade = "Grade A+ (Institutional)" if (rvol >= 1.5 or is_special) and (c_close > ema50) else "Grade A"
            elif is_breakdown:
                signal = "🔴 SWING SELL BREAKDOWN"
                active_breakouts += 1
                trade_logic = f"Breakdown below {sup_level:.2f} | 1:2 R:R Target Set."
                grade = "Grade A+ (Institutional)" if (rvol >= 1.5 or is_special) and (c_close < ema50) else "Grade A"
            else:
                signal = "⚪ ACCUMULATION / RANGE"
                grade = "Neutral"
                trade_logic = "Consolidating within structural boundaries."

            # STRICT 1:2 RISK REWARD RATIO
            sl_dist = 1.0 * atr
            if "SELL" in signal:
                sl = c_close + sl_dist
                target_1 = c_close - (2.0 * sl_dist)
                target_2 = c_close - (3.5 * sl_dist)
            else:
                sl = c_close - sl_dist
                target_1 = c_close + (2.0 * sl_dist)
                target_2 = c_close + (3.5 * sl_dist)

            risk_per_unit = max(abs(c_close - sl), 0.0001)
            units_by_risk = int(risk_per_trade / risk_per_unit)
            units_by_capital = int(available_balance / c_close) if c_close > 0 else 0
            rec_size = min(units_by_risk, units_by_capital)

            if rec_size == 0 and units_by_risk > 0:
                size_str = "0 Units (Balance Low)"
            elif rec_size == 0 and c_close > available_balance:
                size_str = "0 Units (Price > Balance)"
            else:
                size_str = f"{rec_size} Units"

            display_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("^", "").replace("-USD", ""))
            decimals = 4 if (is_special and ("=" in ticker or "USD" in ticker)) else 2

            records.append({
                "Ticker": ticker,
                "Asset": display_name,
                "Signal": signal,
                "Setup Grade": grade,
                "LTP": round(c_close, decimals),
                "VWAP": round(c_vwap, decimals),
                "Breakout_Level": round(res_level if "BUY" in signal else sup_level, decimals),
                "Stop Loss": round(sl, decimals),
                "Target 1 (1:2 Min)": round(target_1, decimals),
                "Target 2 (1:3.5 Ext)": round(target_2, decimals),
                "RVol": rvol_display,
                "RSI": round(rsi, 1),
                "Recommended Size": size_str,
                "Why This Trade": trade_logic,
                "Size": max(1, rec_size) if rec_size > 0 else 1,
                "ActualUnits": rec_size,
                "Decimals": decimals
            })
        except Exception:
            continue

def get_live_candle_data(asset_name):
    for t, mapped in NAME_MAP.items():
        if mapped == asset_name or t == asset_name:
            try:
                t_df = yf.download(t, period="2d", interval="1h", progress=False)
                if not t_df.empty:
                    c = float(t_df['Close'].dropna().iloc[-1])
                    h = float(t_df['High'].dropna().iloc[-1])
                    l = float(t_df['Low'].dropna().iloc[-1])
                    return c, h, l
            except Exception:
                pass
    try:
        t_df = yf.download(f"{asset_name}.NS", period="2d", interval="1h", progress=False)
        if not t_df.empty:
            c = float(t_df['Close'].dropna().iloc[-1])
            h = float(t_df['High'].dropna().iloc[-1])
            l = float(t_df['Low'].dropna().iloc[-1])
            return c, h, l
    except Exception:
        pass
    try:
        t_df = yf.download(asset_name, period="2d", interval="1h", progress=False)
        if not t_df.empty:
            c = float(t_df['Close'].dropna().iloc[-1])
            h = float(t_df['High'].dropna().iloc[-1])
            l = float(t_df['Low'].dropna().iloc[-1])
            return c, h, l
    except Exception:
        pass
    return None, None, None

# -------------------------------------------------------------
# 10. SWING MONITOR (AUTO-UPDATE GOOGLE SHEET ON TP/SL)
# -------------------------------------------------------------
sheet_modified = False

for trade in all_trades:
    if str(trade.get("status", "")).upper() == "OPEN":
        t_id = trade.get("id")
        a_name = trade.get("asset")
        c_ltp, c_high, c_low = get_live_candle_data(a_name)
        
        if c_ltp is None:
            c_ltp = float(trade.get("entry", 0.0))
            c_high = c_ltp
            c_low = c_ltp

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
            exit_time_val = ist_now.strftime("%Y-%m-%d %H:%M")
            pnl_realized = (exit_price_val - e_price) * q if side_type == "BUY" else (e_price - exit_price_val) * q

            idx_list = sheet_trades_df.index[sheet_trades_df["id"] == t_id].tolist()
            if idx_list:
                row_idx = idx_list[0]
                sheet_trades_df.at[row_idx, "status"] = status_val
                sheet_trades_df.at[row_idx, "exit_price"] = exit_price_val
                sheet_trades_df.at[row_idx, "exit_time"] = exit_time_val
                sheet_trades_df.at[row_idx, "pnl"] = pnl_realized
                sheet_modified = True

if sheet_modified:
    save_sheet_trades(sheet_trades_df)
    st.rerun()

# -------------------------------------------------------------
# 11. EOD PERFORMANCE DESK
# -------------------------------------------------------------
today_trades = [t for t in all_trades if str(t.get("date", "")).startswith(today_date_str)]
today_closed = [t for t in today_trades if str(t.get("status", "")).upper() != "OPEN"]

tot_alerts_today = len(today_trades)
tp_hits_today = len([t for t in today_closed if "TARGET_HIT" in str(t.get("status", ""))])
sl_hits_today = len([t for t in today_closed if str(t.get("status", "")).upper() == "SL_HIT"])
today_pnl = sum([float(t.get("pnl", 0.0) or 0.0) for t in today_closed])
win_rate = (tp_hits_today / len(today_closed) * 100) if today_closed else 0.0

def build_eod_message():
    sign = "+" if today_pnl >= 0 else ""
    return (
        f"📊 <b>DAILY EOD SWING TRADING REPORT (1:2 MODEL)</b>\n"
        f"📅 Date: {today_date_str} | 🕒 Time: {ist_now.strftime('%I:%M %p IST')}\n\n"
        f"🔢 Trades Initiated Today: {tot_alerts_today}\n"
        f"🎯 1:2 Targets Hit: {tp_hits_today} ✅\n"
        f"🛑 SL Hit: {sl_hits_today} ❌\n"
        f"📈 Swing Win-Rate: {win_rate:.1f}%\n\n"
        f"💵 Realized P&L: <b>₹{sign}{today_pnl:,.2f}</b>\n"
        f"💼 Available Cash: <b>₹{available_balance:,.2f}</b>\n"
        f"🔒 Locked Margin: <b>₹{blocked_capital:,.2f}</b>\n"
        f"⚡ Total Portfolio Equity: <b>₹{total_portfolio_equity:,.2f}</b>\n\n"
        f"☁️ Sync: Google Sheets Permanent Ledger Active."
    )

# -------------------------------------------------------------
# 12. VIRTUAL SWING PORTFOLIO DESK
# -------------------------------------------------------------
st.markdown("### 💼 Virtual Swing Portfolio (Google Sheet Persistent Desk)")
total_lifetime_pnl = total_portfolio_equity - INITIAL_BASE_CAPITAL

p1, p2, p3, p4 = st.columns([1.5, 1.5, 1.5, 1.2])
with p1:
    st.metric("Available Cash", f"₹{available_balance:,.2f}")
with p2:
    st.metric("Locked in Trades", f"₹{blocked_capital:,.2f}")
with p3:
    st.metric("Total Equity & P&L", f"₹{total_portfolio_equity:,.2f}", delta=f"₹{total_lifetime_pnl:+,.2f}")
with p4:
    st.write("")
    if st.button("🔄 Reset Portfolio"):
        empty_df = pd.DataFrame(columns=SHEET_COLUMNS)
        save_sheet_trades(empty_df)
        st.success("Google Sheet Cleared & Portfolio Reset to ₹10,000!")
        st.rerun()

with st.expander("📊 Today's Performance Report & Telegram Dispatch", expanded=False):
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        st.metric("Today's Trades", tot_alerts_today)
    with e2:
        st.metric("1:2 Targets Hit", f"{tp_hits_today} ✅")
    with e3:
        st.metric("SL Hit", f"{sl_hits_today} ❌")
    with e4:
        st.metric("Today P&L", f"₹{today_pnl:+,.2f}")

    if st.button("📤 Send EOD Report to Telegram Now"):
        ok, res_txt = send_telegram_msg(build_eod_message())
        if ok:
            st.success("✅ EOD Report Telegram par deliver ho gayi!")
        else:
            st.error(f"❌ Telegram Error: {res_txt}")

# Active Running Swing Positions
if open_trades:
    st.markdown("#### ⚡ Active Open Swing Positions (Synced with Google Sheets)")
    for idx, trade in enumerate(open_trades):
        t_id = trade.get("id")
        asset_name = trade.get('asset')
        c_ltp, _, _ = get_live_candle_data(asset_name)
        current_ltp = c_ltp or float(trade.get('entry', 0.0))
        entry_price = float(trade.get('entry', 0.0))
        qty = int(trade.get('qty', 1))
        t_type = str(trade.get('type', "BUY")).upper()
        sl_price = float(trade.get('sl', 0.0))
        tp1_price = float(trade.get('tp1', 0.0))
        inv_amount = float(trade.get("invested_capital", entry_price * qty))

        is_fx = any(fx in str(asset_name).upper() for fx in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "BTC", "ETH", "SOL", "XAU", "XAG", "GOLD", "SILVER"])
        fmt = "{:+,.4f}" if is_fx else "{:+,.2f}"
        disp_fmt = "{:.4f}" if is_fx else "{:.2f}"

        live_pnl = (current_ltp - entry_price) * qty if t_type == "BUY" else (entry_price - current_ltp) * qty
        pnl_color = "#2e7d32" if live_pnl >= 0 else "#c62828"
        pnl_bg = "#e8f5e9" if live_pnl >= 0 else "#ffebee"

        st.markdown(f"""
            <div style="background-color: #1e1e2f; border-left: 5px solid {pnl_color}; padding: 12px; border-radius: 6px; margin-bottom: 10px; color: #ffffff;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="font-size: 16px;">{asset_name}</strong> 
                        <span style="background: {'#1b5e20' if t_type=='BUY' else '#b71c1c'}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-left: 6px;">{t_type}</span>
                        <span style="color: #ffb74d; font-size: 12px; margin-left: 10px;">🔒 Locked: ₹{inv_amount:,.2f}</span>
                        <span style="color: #90caf9; font-size: 11px; margin-left: 10px;">Entry: {trade.get('date')}</span>
                    </div>
                    <div style="font-size: 15px; font-weight: bold; color: {pnl_color}; background: {pnl_bg}; padding: 2px 8px; border-radius: 4px;">
                        P&L: {fmt.format(live_pnl)}
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 8px; font-size: 12px; color: #b0bec5;">
                    <span>Qty: <b>{qty}</b></span>
                    <span>Entry: <b>{disp_fmt.format(entry_price)}</b></span>
                    <span>LTP: <b style="color: #fff;">{disp_fmt.format(current_ltp)}</b></span>
                    <span>SL: <b style="color: #ef5350;">{disp_fmt.format(sl_price)}</b></span>
                    <span>Target 1 (1:2): <b style="color: #66bb6a;">{disp_fmt.format(tp1_price)}</b></span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        col_sq1, col_sq2 = st.columns([6, 1])
        with col_sq2:
            if st.button(f"🔴 Exit #{idx+1}", key=f"exit_pos_{t_id}"):
                pnl_realized = (current_ltp - entry_price) * qty if t_type == "BUY" else (entry_price - current_ltp) * qty
                idx_list = sheet_trades_df.index[sheet_trades_df["id"] == t_id].tolist()
                if idx_list:
                    row_idx = idx_list[0]
                    sheet_trades_df.at[row_idx, "status"] = "MANUAL_EXIT"
                    sheet_trades_df.at[row_idx, "exit_price"] = current_ltp
                    sheet_trades_df.at[row_idx, "exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
                    sheet_trades_df.at[row_idx, "pnl"] = pnl_realized
                    save_sheet_trades(sheet_trades_df)
                    st.success("Position closed and saved to Google Sheets!")
                    st.rerun()

# -------------------------------------------------------------
# 13. METRICS & MONITORING TABLE
# -------------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Universe Tracked", len(tickers))
with m2:
    st.metric("Active Breakouts", active_breakouts)
with m3:
    st.metric("Available Balance", f"₹{available_balance:,.2f}")
with m4:
    st.metric("Active Timeframe", swing_tf)

if records:
    df_display = pd.DataFrame(records).drop(columns=["Ticker", "Size", "ActualUnits", "VWAP", "Breakout_Level", "Decimals"])
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info(f"Scanning {selected_universe} on **{swing_tf}**. No swing setups matching strict 1:2 breakout parameters at this bar.")

# -------------------------------------------------------------
# 14. DUAL ORDER EXECUTION DESK
# -------------------------------------------------------------
st.markdown("### ⚡ Order Execution Desk (Dual Engine: Paper + Real Broker)")
ord_col1, ord_col2, ord_col3, ord_col4 = st.columns([1.8, 1.2, 1.2, 1.8])

records_assets = [r["Asset"] for r in records] if records else []
all_extra_assets = [NAME_MAP.get(t, t.replace(".NS", "").replace("^", "").replace("-USD", "")) for t in tickers]
available_clean_names = sorted(list(set(records_assets + all_extra_assets)))

with ord_col1:
    chosen_asset = st.selectbox("Contract / Asset:", available_clean_names if available_clean_names else ["None"])

selected_item = next((r for r in records if r["Asset"] == chosen_asset), None)
live_val_tuple = get_live_candle_data(chosen_asset)
live_val = live_val_tuple[0] or 100.0

default_ltp = selected_item["LTP"] if selected_item else live_val
default_sl = selected_item["Stop Loss"] if selected_item else round(default_ltp * 0.98, 4 if ("=" in str(chosen_asset) or "USD" in str(chosen_asset)) else 2)
default_tp = selected_item["Target 1 (1:2 Min)"] if selected_item else round(default_ltp * 1.04, 4 if ("=" in str(chosen_asset) or "USD" in str(chosen_asset)) else 2)

is_forex_asset = any(fx in str(chosen_asset).upper() for fx in [
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "INR", "GOLD", "SILVER", "XAU", "XAG", "GAS"
])
dec_format = "%.4f" if is_forex_asset else "%.2f"
dec_step = 0.0001 if is_forex_asset else 0.05
min_val = 0.0001 if is_forex_asset else 0.01

auto_units_by_capital = int(available_balance / default_ltp) if default_ltp > 0 else 0
auto_suggested_qty = selected_item["Size"] if selected_item else min(1, auto_units_by_capital)
default_order_qty = max(1, min(auto_suggested_qty, auto_units_by_capital)) if auto_units_by_capital > 0 else 1

with ord_col2:
    side = st.selectbox("Direction:", ["BUY", "SELL"])

with ord_col3:
    qty_input = st.number_input("Qty / Lots:", min_value=1, value=default_order_qty, step=1)

with ord_col4:
    custom_exec_price = st.number_input("Execution Price:", min_value=min_val, value=float(default_ltp), step=dec_step, format=dec_format)

sl_tp_col1, sl_tp_col2 = st.columns(2)
with sl_tp_col1:
    custom_sl = st.number_input("Stop Loss (SL):", min_value=min_val, value=float(default_sl), step=dec_step, format=dec_format)
with sl_tp_col2:
    custom_tp = st.number_input("Target Price (TP - 1:2):", min_value=min_val, value=float(default_tp), step=dec_step, format=dec_format)

required_fund = float(custom_exec_price * qty_input)

if required_fund > available_balance:
    st.warning(f"⚠️ **Required Fund:** ₹{required_fund:,.2f} | **Available Balance:** ₹{available_balance:,.2f} (Insufficient Balance)")
else:
    st.success(f"✅ **Required Fund:** ₹{required_fund:,.2f} | **Available Balance:** ₹{available_balance:,.2f}")

st.write("")
btn_col1, btn_col2 = st.columns(2)

with btn_col1:
    if st.button("📥 Record Virtual Swing Trade", use_container_width=True):
        if required_fund > available_balance:
            st.error(f"❌ **Trade Rejected!** Balance ₹{available_balance:,.2f} is less than required ₹{required_fund:,.2f}.")
        else:
            new_id = int(sheet_trades_df["id"].max() + 1) if not sheet_trades_df.empty and pd.notnull(sheet_trades_df["id"].max()) else 1
            new_row = pd.DataFrame([{
                "id": new_id,
                "date": ist_now.strftime("%Y-%m-%d %H:%M"),
                "asset": chosen_asset,
                "type": side,
                "entry": custom_exec_price,
                "sl": custom_sl,
                "tp1": custom_tp,
                "tp2": selected_item.get("Target 2 (1:3.5 Ext)", custom_tp) if selected_item else custom_tp,
                "qty": qty_input,
                "invested_capital": required_fund,
                "status": "OPEN",
                "timeframe": swing_tf,
                "exit_price": 0.0,
                "exit_time": "",
                "pnl": 0.0
            }])
            updated_df = pd.concat([sheet_trades_df, new_row], ignore_index=True)
            save_sheet_trades(updated_df)
            st.success(f"✅ Trade #{new_id} permanently saved in Google Sheet!")
            st.rerun()

with btn_col2:
    if st.button("🚀 Fire Real Order (Angel One Delivery)", use_container_width=True):
        if is_beginner:
            st.error("Beginner mode me Real Trading locked hai. Top se 'Pro Trader' chunein.")
        else:
            raw_sym = selected_item["Ticker"] if selected_item else chosen_asset
            exch = "NSE" if ".NS" in raw_sym or "^NSE" in raw_sym else "MCX"
            clean_sym = raw_sym.replace(".NS", "").replace("^", "")

            ok, msg = place_order_smartapi(
                symbol_token=clean_sym,
                trading_symbol=clean_sym,
                exchange=exch,
                qty=qty_input,
                transaction_type=side,
                price=custom_exec_price
            )
            if ok:
                st.success(f"🟢 REAL BROKER ORDER: {msg}")
            else:
                st.error(f"🔴 REAL BROKER ORDER FAILED: {msg}")

# -------------------------------------------------------------
# 15. COMPLETED TRADE HISTORY LEDGER
# -------------------------------------------------------------
if closed_trades:
    with st.expander("📜 Completed Paper Trades Ledger (From Google Sheets)", expanded=False):
        history_df = pd.DataFrame(closed_trades)[["id", "date", "asset", "type", "entry", "exit_price", "qty", "pnl", "status", "exit_time"]]
        st.dataframe(history_df, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 16. TRADINGVIEW LIVE CHART
# -------------------------------------------------------------
st.markdown("### 📈 Interactive TradingView Live Chart")
tv_symbol_map = {
    "ALPHABET (GOOGLE)": "NASDAQ:GOOGL",
    "NVIDIA": "NASDAQ:NVDA",
    "TESLA": "NASDAQ:TSLA",
    "APPLE": "NASDAQ:AAPL",
    "MICROSOFT": "NASDAQ:MSFT",
    "AMAZON": "NASDAQ:AMZN",
    "META PLATFORMS": "NASDAQ:META",
    "NIFTY 50": "NSE:NIFTY",
    "BANK NIFTY": "NSE:BANKNIFTY",
    "XAUUSD (Gold)": "TVC:GOLD",
    "XAGUSD (Silver)": "TVC:SILVER",
    "CRUDE OIL": "TVC:USOIL",
    "COPPER": "COMEX:HG1!",
    "NATURAL GAS": "NYMEX:NG1!",
    "USD/INR": "FX_IDC:USDINR",
    "EUR/USD": "FX:EURUSD",
    "GBP/USD": "FX:GBPUSD",
    "USD/JPY": "FX:USDJPY",
    "AUD/USD": "FX:AUDUSD",
    "USD/CAD": "FX:USDCAD",
    "USD/CHF": "FX:USDCHF",
    "NZD/USD": "FX:NZDUSD",
    "EUR/GBP": "FX:EURGBP",
    "EUR/JPY": "FX:EURJPY",
    "GBP/JPY": "FX:GBPJPY",
    "BITCOIN": "BINANCE:BTCUSDT",
    "ETHEREUM": "BINANCE:ETHUSDT",
    "SOLANA": "BINANCE:SOLUSDT"
}

chart_asset = st.selectbox("Chart Asset:", available_clean_names if available_clean_names else ["NIFTY 50"], key="tv_select")

if chart_asset in tv_symbol_map:
    tv_symbol = tv_symbol_map[chart_asset]
else:
    found_t = None
    for t, m in NAME_MAP.items():
        if m == chart_asset:
            found_t = t
            break
    if found_t:
        if ".NS" in found_t:
            tv_symbol = "NSE:" + found_t.replace(".NS", "")
        else:
            tv_symbol = "NASDAQ:" + found_t
    else:
        tv_symbol = "NSE:" + chart_asset.replace(".NS", "")

tv_interval = curr_tf_conf["tv"]

tv_code = f"""
<div class="tradingview-widget-container" style="height:550px; width:100%;">
  <div id="tradingview_chart" style="height:550px;"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{
    "autosize": true,
    "symbol": "{tv_symbol}",
    "interval": "{tv_interval}",
    "timezone": "Asia/Kolkata",
    "theme": "dark",
    "style": "1",
    "locale": "en",
    "toolbar_bg": "#131722",
    "enable_publishing": false,
    "hide_side_toolbar": false,
    "allow_symbol_change": true,
    "container_id": "tradingview_chart"
  }});
  </script>
</div>
"""
components.html(tv_code, height=560)
