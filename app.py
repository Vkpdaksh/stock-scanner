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

# -------------------------------------------------------------
# 1. PAGE SETUP & CONFIG
# -------------------------------------------------------------
st.set_page_config(
    page_title="Institutional Trading Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

CONFIG_FILE = "system_mode.json"
PAPER_TRADES_FILE = "paper_trades.json"
EOD_FLAG_FILE = "eod_sent_flag.json"

TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_ID = "1527960238"

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

system_config = load_json(CONFIG_FILE, {"mode": "Pro Trader (Full)", "execution": "Virtual Paper Trading"})
paper_data = load_json(PAPER_TRADES_FILE, {"balance": 10000, "trades": []})
eod_tracker = load_json(EOD_FLAG_FILE, {"last_sent_date": ""})

def get_ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

def send_telegram_msg(msg_text):
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
# 2. ANGEL ONE SMARTAPI SESSION ENGINE
# -------------------------------------------------------------
def get_secret(key_name):
    try:
        if hasattr(st, "secrets") and key_name in st.secrets:
            return str(st.secrets[key_name])
    except Exception:
        pass
    return os.environ.get(key_name, "")

ANGEL_API_KEY = get_secret("ANGEL_API_KEY")
ANGEL_CLIENT_ID = get_secret("ANGEL_CLIENT_ID")
ANGEL_MPIN = get_secret("ANGEL_MPIN")
ANGEL_TOTP_KEY = get_secret("ANGEL_TOTP_KEY")

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
        return False, "SmartAPI credentials missing! Add Angel One secrets or use Paper Desk."
    try:
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": trading_symbol,
            "symboltoken": str(symbol_token),
            "transactiontype": transaction_type,
            "ordertype": "LIMIT" if price > 0 else "MARKET",
            "price": str(price) if price > 0 else "0",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "quantity": str(qty),
            "exchange": exchange
        }
        res = api.placeOrder(order_params)
        if res.get("status"):
            return True, f"Real Order Executed! Order ID: {res.get('data', {}).get('orderid')}"
        return False, res.get("message", "Order rejected by broker.")
    except Exception as e:
        return False, str(e)

# -------------------------------------------------------------
# 3. WATCHLISTS & ASSETS
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
# 4. TOP HEADER & PROFILE SWITCHER
# -------------------------------------------------------------
st.title("⚡ Institutional Grade Trading Terminal")

ist_now = get_ist_now()
time_str = ist_now.strftime("%I:%M:%S %p IST")
today_date_str = ist_now.strftime("%Y-%m-%d")
cur_mins = ist_now.hour * 60 + ist_now.minute

is_nse_open = (ist_now.weekday() < 5) and (555 <= cur_mins <= 930)
session_text = "🟢 NSE SESSION OPEN" if is_nse_open else "🔴 NSE SESSION CLOSED"

col_mode, col_exec = st.columns([2, 2])

with col_mode:
    selected_mode = st.selectbox(
        "👤 Select Profile Mode:",
        ["Beginner (Safe)", "Pro Trader (Full)"],
        index=1 if system_config.get("mode") == "Pro Trader (Full)" else 0
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

if system_config.get("mode") != selected_mode or system_config.get("execution") != execution_type:
    system_config["mode"] = selected_mode
    system_config["execution"] = execution_type
    save_json(CONFIG_FILE, system_config)

st.caption(f"Status: **{session_text}** | Live Feed: **{time_str}** | Profile: **{selected_mode}**")

# -------------------------------------------------------------
# 5. RISK ALLOCATION & CAPITAL DESK
# -------------------------------------------------------------
st.markdown("### 🛡️ Risk Management & Capital Allocation Desk")
r_col1, r_col2, r_col3, r_col4 = st.columns(4)

current_balance = paper_data.get("balance", 10000)

with r_col1:
    account_capital = st.number_input("Account Capital (₹):", min_value=1000, value=int(current_balance), step=1000)

with r_col2:
    risk_pct_choice = st.selectbox("Max Risk Per Trade (%):", [1.0, 1.5, 2.0, 3.0], index=0)

safe_budget = (account_capital * risk_pct_choice) / 100.0

with r_col3:
    risk_per_trade = st.number_input("Risk Per Position (₹):", min_value=50.0, value=float(safe_budget), step=25.0)

with r_col4:
    max_daily_loss = st.number_input("Max Daily Loss Cap (₹):", min_value=100.0, value=float(safe_budget * 3), step=50.0)

actual_risk_pct = (risk_per_trade / account_capital) * 100 if account_capital > 0 else 0

if actual_risk_pct > 2.0:
    st.error(f"🚨 **High Risk Alert:** Selected risk is **{actual_risk_pct:.1f}%** of capital! Keep risk under 2% (₹{safe_budget:.0f}).")
else:
    st.success(f"✅ **Disciplined Risk:** Risk is **{actual_risk_pct:.1f}%** (₹{risk_per_trade:.0f} per trade | Daily Max Loss: ₹{max_daily_loss:.0f}).")

st.markdown("---")

# -------------------------------------------------------------
# 6. MARKET UNIVERSE SELECTOR
# -------------------------------------------------------------
available_universes = list(MARKET_UNIVERSES.keys())

if 555 <= cur_mins <= 930:
    default_univ_index = available_universes.index("Indian Equities & Indices (NSE)")
elif 930 < cur_mins <= 1290:
    default_univ_index = available_universes.index("Forex & Commodities")
else:
    default_univ_index = available_universes.index("US Equities (NASDAQ/NYSE)")

selected_universe = st.selectbox("Active Asset Universe (Auto-Switches by Time):", available_universes, index=default_univ_index)
tickers = MARKET_UNIVERSES[selected_universe]

@st.cache_data(ttl=60)
def fetch_market_data(ticker_list):
    try:
        return yf.download(ticker_list, period="5d", interval="15m", group_by='ticker', progress=False)
    except Exception:
        return None

raw_data = fetch_market_data(tickers) if tickers else None
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

            ema20 = float(ta.trend.ema_indicator(df['Close'], window=20).dropna().iloc[-1])
            ema50 = float(ta.trend.ema_indicator(df['Close'], window=50).dropna().iloc[-1])

            is_special = ("=" in ticker or "^" in ticker or "-USD" in ticker)
            rvol = (c_vol / avg_vol) if avg_vol > 0 else 1.0
            rvol_display = "Liquid" if is_special else f"{round(rvol, 2)}x"

            is_breakout = (c_close > res_level) and (c_close > c_open) and (c_close > ema20)
            is_breakdown = (c_close < sup_level) and (c_close < c_open) and (c_close < ema20)

            if is_breakout:
                signal = "🟢 BUY BREAKOUT"
                active_breakouts += 1
                trade_logic = f"Closed above resistance ({res_level:.4f if is_special else res_level:.2f}) with VWAP support."
                if (rvol >= 2.0 or is_special) and (c_close > ema50) and (rsi >= 58):
                    grade = "Grade A+ (Sniper)"
                elif (rvol >= 1.3 or is_special) and (rsi >= 52):
                    grade = "Grade A (Inst.)"
                else:
                    grade = "Grade B (Scalp)"
            elif is_breakdown:
                signal = "🔴 SELL BREAKDOWN"
                active_breakouts += 1
                trade_logic = f"Closed below support ({sup_level:.4f if is_special else sup_level:.2f}) with bearish pressure."
                if (rvol >= 2.0 or is_special) and (c_close < ema50) and (rsi <= 42):
                    grade = "Grade A+ (Sniper)"
                elif (rvol >= 1.3 or is_special) and (rsi <= 48):
                    grade = "Grade A (Inst.)"
                else:
                    grade = "Grade B (Scalp)"
            else:
                signal = "⚪ CONSOLIDATION"
                grade = "Neutral"
                trade_logic = "Price oscillating within normal range."

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
                "Target 1 (1:1)": round(target_1, decimals),
                "Target 2 (1:2)": round(target_2, decimals),
                "RVol": rvol_display,
                "RSI": round(rsi, 1),
                "Recommended Size": f"{rec_size} Units",
                "Why This Trade": trade_logic,
                "Size": rec_size,
                "Decimals": decimals
            })
        except Exception:
            continue

def get_live_price_for_asset(asset_name):
    m = next((r for r in records if r["Asset"] == asset_name), None)
    if m:
        return m["LTP"]
    for t, mapped in NAME_MAP.items():
        if mapped == asset_name or t == asset_name:
            try:
                t_df = yf.download(t, period="1d", interval="15m", progress=False)
                if not t_df.empty:
                    return float(t_df['Close'].dropna().iloc[-1])
            except Exception:
                pass
    try:
        t_df = yf.download(f"{asset_name}.NS", period="1d", interval="15m", progress=False)
        if not t_df.empty:
            return float(t_df['Close'].dropna().iloc[-1])
    except Exception:
        pass
    try:
        t_df = yf.download(asset_name, period="1d", interval="15m", progress=False)
        if not t_df.empty:
            return float(t_df['Close'].dropna().iloc[-1])
    except Exception:
        pass
    return None

# -------------------------------------------------------------
# 7. AUTO SL, TP & 3:15 PM INDIAN MARKET SQUARE OFF ENGINE
# -------------------------------------------------------------
all_trades = paper_data.get("trades", [])
needs_save = False

# 3:15 PM square off check
is_past_315 = (ist_now.hour > 15) or (ist_now.hour == 15 and ist_now.minute >= 15) or (ist_now.hour < 9)

for trade in all_trades:
    if trade.get("status") == "OPEN":
        a_name = trade.get("asset")
        c_ltp = get_live_price_for_asset(a_name) or trade.get("entry")
        e_price = trade.get("entry")
        s_price = trade.get("sl")
        t_price = trade.get("tp1")
        q = trade.get("qty")
        side_type = trade.get("type")
        trade_date = trade.get("date", "")[:10]

        sl_hit = (side_type == "BUY" and c_ltp <= s_price) or (side_type == "SELL" and c_ltp >= s_price)
        tp_hit = (side_type == "BUY" and c_ltp >= t_price) or (side_type == "SELL" and c_ltp <= t_price)
        
        is_global_asset = any(fx in str(a_name).upper() for fx in [
            "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", 
            "BTC", "ETH", "SOL", "XAU", "XAG", "CRUDE", "COPPER", "GOLD", "SILVER", "GAS",
            "GOOGLE", "ALPHABET", "GOOGL", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "AMD", "NFLX", "PLTR",
            "AVGO", "SMCI", "ARM", "QCOM", "INTC", "MU", "PANW", "CRWD", "COIN", "MSTR"
        ])

        # 3:15 PM Square off ONLY applies to Indian Equities
        if is_global_asset:
            intraday_expired = False
        else:
            intraday_expired = (trade_date != today_date_str) or is_past_315

        if sl_hit or tp_hit or intraday_expired:
            if sl_hit:
                trade["status"] = "SL_HIT"
            elif tp_hit:
                trade["status"] = "TARGET_HIT"
            else:
                trade["status"] = "INTRADAY_AUTO_SQUAREOFF (3:15 PM)"

            trade["exit_price"] = c_ltp
            trade["exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
            pnl_realized = (c_ltp - e_price) * q if side_type == "BUY" else (e_price - c_ltp) * q
            trade["pnl"] = pnl_realized
            paper_data["balance"] += pnl_realized
            needs_save = True

if needs_save:
    save_json(PAPER_TRADES_FILE, paper_data)
    st.rerun()

# -------------------------------------------------------------
# 8. VIRTUAL PORTFOLIO & ACTIVE POSITIONS
# -------------------------------------------------------------
st.markdown("### 💼 Virtual Paper Trading Portfolio (₹10,000 Capital Desk)")
current_balance = paper_data.get("balance", 10000)
total_pnl = current_balance - 10000

open_trades = [t for t in all_trades if t.get("status") == "OPEN"]
closed_trades = [t for t in all_trades if t.get("status") != "OPEN"]

p1, p2, p3, p4 = st.columns([1.5, 1.5, 1.5, 1.2])
with p1:
    st.metric("Virtual Cash Balance", f"₹{current_balance:,.2f}")
with p2:
    st.metric("Total Paper P&L", f"₹{total_pnl:+,.2f}", delta=f"₹{total_pnl:+,.2f}")
with p3:
    st.metric("Open / Closed Trades", f"{len(open_trades)} Open | {len(closed_trades)} Closed")
with p4:
    st.write("")
    if st.button("🔄 Reset to ₹10k"):
        paper_data = {"balance": 10000, "trades": []}
        save_json(PAPER_TRADES_FILE, paper_data)
        st.success("Balance reset to ₹10,000!")
        st.rerun()

# Active Positions Display
if open_trades:
    st.markdown("#### ⚡ Active Open Positions (Running Trades)")
    for idx, trade in enumerate(open_trades):
        asset_name = trade.get('asset')
        current_ltp = get_live_price_for_asset(asset_name) or trade.get('entry')
        
        entry_price = trade.get('entry')
        qty = trade.get('qty')
        t_type = trade.get('type')
        sl_price = trade.get('sl')
        tp1_price = trade.get('tp1')
        
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
                    <span>Target 1: <b style="color: #66bb6a;">{disp_fmt.format(tp1_price)}</b></span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        col_sq1, col_sq2 = st.columns([6, 1])
        with col_sq2:
            if st.button(f"🔴 Exit #{idx+1}", key=f"sq_off_{idx}"):
                trade["status"] = "MANUAL_EXIT"
                trade["exit_price"] = current_ltp
                trade["exit_time"] = ist_now.strftime("%Y-%m-%d %H:%M")
                pnl_realized = (current_ltp - entry_price) * qty if t_type == "BUY" else (entry_price - current_ltp) * qty
                trade["pnl"] = pnl_realized
                paper_data["balance"] += pnl_realized
                save_json(PAPER_TRADES_FILE, paper_data)
                st.success(f"Closed {asset_name} position!")
                st.rerun()

# -------------------------------------------------------------
# 9. METRICS & MONITORING TABLE
# -------------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Universe Tracked", len(tickers))
with m2:
    st.metric("Active Breakouts", active_breakouts)
with m3:
    st.metric("Risk Budget", f"₹{risk_per_trade:.0f}")
with m4:
    st.metric("Active Route", selected_mode)

if records:
    df_display = pd.DataFrame(records).drop(columns=["Ticker", "Size", "VWAP", "Breakout_Level", "Decimals"])
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info(f"Currently tracking {selected_universe}. No active breakout setups found at this candle.")

# -------------------------------------------------------------
# 10. DUAL ORDER EXECUTION DESK (PAPER & REAL BROKER)
# -------------------------------------------------------------
st.markdown("### ⚡ Order Execution Desk (Dual Engine: Paper + Real Broker)")
ord_col1, ord_col2, ord_col3, ord_col4 = st.columns([1.8, 1.2, 1.2, 1.8])

records_assets = [r["Asset"] for r in records] if records else []
all_extra_assets = [NAME_MAP.get(t, t.replace(".NS", "").replace("^", "").replace("-USD", "")) for t in tickers]
available_clean_names = sorted(list(set(records_assets + all_extra_assets)))

with ord_col1:
    chosen_asset = st.selectbox("Contract / Asset:", available_clean_names if available_clean_names else ["None"])

selected_item = next((r for r in records if r["Asset"] == chosen_asset), None)
live_val = get_live_price_for_asset(chosen_asset) or 100.0

default_ltp = selected_item["LTP"] if selected_item else live_val
default_sl = selected_item["Stop Loss"] if selected_item else round(default_ltp * 0.99, 4 if ("=" in str(chosen_asset) or "USD" in str(chosen_asset)) else 2)
default_tp = selected_item["Target 1 (1:1)"] if selected_item else round(default_ltp * 1.01, 4 if ("=" in str(chosen_asset) or "USD" in str(chosen_asset)) else 2)

is_forex_asset = any(fx in str(chosen_asset).upper() for fx in [
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "INR", "GOLD", "SILVER", "XAU", "XAG", "GAS"
])
dec_format = "%.4f" if is_forex_asset else "%.2f"
dec_step = 0.0001 if is_forex_asset else 0.05
min_val = 0.0001 if is_forex_asset else 0.01

if selected_item:
    vwap_val = selected_item.get("VWAP", default_ltp)
    brk_lvl = selected_item.get("Breakout_Level", default_ltp)
    sig_type = selected_item.get("Signal", "")
    
    if "BUY" in sig_type:
        dist_pct = ((default_ltp - brk_lvl) / brk_lvl) * 100
        if default_ltp < vwap_val:
            st.error("🔴 **Setup Invalidated:** Price VWAP ke niche gir chuka hai. Entry avoid karein.")
        elif dist_pct > 0.4:
            st.warning(f"🟡 **Overextended (+{dist_pct:.2f}%):** Retest ka wait karein.")
        else:
            st.success(f"🟢 **Safe Entry Zone (+{dist_pct:.2f}%):** Tight SL ke sath entry valid hai.")
    elif "SELL" in sig_type:
        dist_pct = ((brk_lvl - default_ltp) / brk_lvl) * 100
        if default_ltp > vwap_val:
            st.error("🔴 **Setup Invalidated:** Price VWAP ke upar ja chuka hai.")
        elif dist_pct > 0.4:
            st.warning(f"🟡 **Overextended (-{dist_pct:.2f}%):** Retest ka wait karein.")
        else:
            st.success(f"🟢 **Safe Entry Zone (-{dist_pct:.2f}%):** Short entry valid hai.")

with ord_col2:
    side = st.selectbox("Direction:", ["BUY", "SELL"])

with ord_col3:
    suggested_qty = selected_item["Size"] if selected_item else 1
    qty_input = st.number_input("Qty / Lots:", min_value=1, value=max(1, suggested_qty), step=1)

with ord_col4:
    custom_exec_price = st.number_input("Execution Price:", min_value=min_val, value=float(default_ltp), step=dec_step, format=dec_format)

sl_tp_col1, sl_tp_col2 = st.columns(2)
with sl_tp_col1:
    custom_sl = st.number_input("Stop Loss (SL):", min_value=min_val, value=float(default_sl), step=dec_step, format=dec_format)
with sl_tp_col2:
    custom_tp = st.number_input("Target Price (TP):", min_value=min_val, value=float(default_tp), step=dec_step, format=dec_format)

st.write("")
btn_col1, btn_col2 = st.columns(2)

with btn_col1:
    if st.button("📥 Record Virtual Paper Trade", use_container_width=True):
        new_trade = {
            "date": ist_now.strftime("%Y-%m-%d %H:%M"),
            "asset": chosen_asset,
            "type": side,
            "entry": custom_exec_price,
            "sl": custom_sl,
            "tp1": custom_tp,
            "tp2": selected_item.get("Target 2 (1:2)", custom_tp) if selected_item else custom_tp,
            "qty": qty_input,
            "status": "OPEN"
        }
        paper_data["trades"].append(new_trade)
        save_json(PAPER_TRADES_FILE, paper_data)
        st.success(f"✅ Virtual {side} Recorded for {chosen_asset} at {custom_exec_price} | SL: {custom_sl} | TP: {custom_tp}!")
        st.rerun()

with btn_col2:
    if st.button("🚀 Fire Real Order (Angel One)", use_container_width=True):
        if is_beginner:
            st.error("Beginner mode me Real Trading locked hai. Top profile se 'Pro Trader (Full)' select karein.")
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
# 11. COMPLETED TRADE HISTORY LEDGER
# -------------------------------------------------------------
if closed_trades:
    with st.expander("📜 Completed Paper Trades Ledger", expanded=False):
        history_df = pd.DataFrame(closed_trades)
        st.dataframe(history_df, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 12. TRADINGVIEW LIVE CHART (FIXED SYMBOLS FOR ALL ASSETS)
# -------------------------------------------------------------
st.markdown("### 📈 Interactive TradingView Live Chart")

c_sel_col1, c_sel_col2 = st.columns([3, 1])
with c_sel_col1:
    chart_asset = st.selectbox("Select Asset to View Chart:", available_clean_names if available_clean_names else ["ALPHABET (GOOGLE)"])

# Exact TradingView symbol resolution
tv_symbol_map = {
    "ALPHABET (GOOGLE)": "NASDAQ:GOOGL",
    "GOOGLE": "NASDAQ:GOOGL",
    "GOOGL": "NASDAQ:GOOGL",
    "NVIDIA": "NASDAQ:NVDA",
    "NVDA": "NASDAQ:NVDA",
    "TESLA": "NASDAQ:TSLA",
    "TSLA": "NASDAQ:TSLA",
    "APPLE": "NASDAQ:AAPL",
    "AAPL": "NASDAQ:AAPL",
    "MICROSOFT": "NASDAQ:MSFT",
    "MSFT": "NASDAQ:MSFT",
    "AMAZON": "NASDAQ:AMZN",
    "AMZN": "NASDAQ:AMZN",
    "META PLATFORMS": "NASDAQ:META",
    "META": "NASDAQ:META",
    "AMD": "NASDAQ:AMD",
    "NFLX": "NASDAQ:NFLX",
    "PLTR": "NASDAQ:PLTR",
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

tv_interval = "15"

with c_sel_col2:
    st.caption(f"TradingView Code: **{tv_symbol}** | Timeframe: **{tv_interval}m**")

tv_code = f"""
<div class="tradingview-widget-container" style="height:550px; width:100%;">
  <div id="tradingview_chart" style="height:550px;"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget(
  {{
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
  }}
  );
  </script>
</div>
"""
components.html(tv_code, height=560)
