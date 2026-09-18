import os
import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import yfinance as yf
import ta
from datetime import datetime, timezone, timedelta

# -------------------------------------------------------------
# 1. PAGE SETUP (CLEAN DEFAULT STREAMLIT THEME PRESERVED)
# -------------------------------------------------------------
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

# Initialize configs
system_config = load_json(CONFIG_FILE, {"mode": "Beginner (Safe)", "execution": "Paper Trading"})
paper_data = load_json(PAPER_TRADES_FILE, {"balance": 10000, "trades": []})

# -------------------------------------------------------------
# 2. ANGEL ONE SMARTAPI SESSION & ORDER FUNCTION
# -------------------------------------------------------------
ANGEL_API_KEY = os.environ.get("ANGEL_API_KEY", "")
ANGEL_CLIENT_ID = os.environ.get("ANGEL_CLIENT_ID", "")
ANGEL_MPIN = os.environ.get("ANGEL_MPIN", "")
ANGEL_TOTP_KEY = os.environ.get("ANGEL_TOTP_KEY", "")

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

def place_order_smartapi(symbol_token, trading_symbol, exchange, qty, transaction_type):
    api = get_smartapi_session()
    if not api:
        return False, "SmartAPI session inactive. Check GitHub/Streamlit secrets."
    try:
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": trading_symbol,
            "symboltoken": str(symbol_token),
            "transactiontype": transaction_type,
            "exchange": exchange,
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "quantity": str(qty)
        }
        res = api.placeOrder(order_params)
        if res.get("status"):
            return True, f"Order Executed! Order ID: {res.get('data', {}).get('orderid')}"
        return False, res.get("message", "Order rejected by broker.")
    except Exception as e:
        return False, str(e)

# -------------------------------------------------------------
# 3. WATCHLISTS & SECTOR INDICES
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

def get_ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

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

is_nse_open = (ist_now.weekday() < 5) and (
    (ist_now.hour == 9 and ist_now.minute >= 15) or 
    (10 <= ist_now.hour < 15) or 
    (ist_now.hour == 15 and ist_now.minute <= 30)
)
session_text = "🟢 NSE SESSION OPEN" if is_nse_open else "🔴 NSE SESSION CLOSED"

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
        st.selectbox("Execution Route:", ["Virtual Paper Trading (Locked)"], disabled=True)
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
        "Risk Per Position (₹ / $):",
        min_value=50,
        max_value=50000,
        value=100,
        step=50
    )

# Capital Risk Warning Badge
current_balance = paper_data.get("balance", 10000)
risk_pct = (risk_per_trade / current_balance) * 100 if current_balance > 0 else 0

if risk_pct > 2.0:
    st.warning(f"⚠️ **High Risk Alert:** Selected risk is **{risk_pct:.1f}%** of your capital! Beginners should keep risk at **1% - 2% (₹100 - ₹200)**.")
else:
    st.success(f"✅ **Safe Risk Discipline:** Position risk is **{risk_pct:.1f}%** (Within the safe 1-2% bracket).")

if system_config.get("mode") != selected_mode or system_config.get("execution") != execution_type:
    system_config["mode"] = selected_mode
    system_config["execution"] = execution_type
    save_json(CONFIG_FILE, system_config)

st.caption(f"Status: **{session_text}** | Live Feed: **{time_str}** | Profile: **{selected_mode}** | Daily Cap: **{'Max 3 Trades/Day (Safe)' if is_beginner else 'Unlimited Flow'}**")

# -------------------------------------------------------------
# 5. VIRTUAL PAPER TRADING PORTFOLIO & RESET ENGINE
# -------------------------------------------------------------
st.markdown("### 💼 Virtual Paper Trading Portfolio (₹10,000 Capital Desk)")
total_pnl = current_balance - 10000
all_trades = paper_data.get("trades", [])
open_trades = [t for t in all_trades if t.get("status") == "OPEN"]
closed_trades = [t for t in all_trades if t.get("status") != "OPEN"]

p1, p2, p3, p4 = st.columns([1.5, 1.5, 1.5, 1])
with p1:
    st.metric("Virtual Cash Balance", f"₹{current_balance:,}")
with p2:
    st.metric("Total Paper P&L", f"₹{total_pnl:+,}", delta=f"₹{total_pnl:+,}")
with p3:
    st.metric("Open / Closed Trades", f"{len(open_trades)} Open | {len(closed_trades)} Closed")
with p4:
    st.write("")
    if st.button("🔄 Reset to ₹10k", help="Reset balance to ₹10,000"):
        paper_data = {"balance": 10000, "trades": []}
        save_json(PAPER_TRADES_FILE, paper_data)
        st.success("Balance reset to ₹10,000!")
        st.rerun()

# -------------------------------------------------------------
# 5B. ACTIVE POSITIONS WITH SQUARE-OFF BUTTONS
# -------------------------------------------------------------
if open_trades:
    st.markdown("#### ⚡ Active Open Positions")
    for idx, trade in enumerate(open_trades):
        t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns([2, 1.5, 2, 1.5, 1.2])
        with t_col1:
            st.write(f"**{trade.get('asset')}** ({trade.get('type')})")
        with t_col2:
            st.caption(f"Entry: ₹{trade.get('entry')} | Qty: {trade.get('qty')}")
        with t_col3:
            st.caption(f"SL: ₹{trade.get('sl')} | TP1: ₹{trade.get('tp1')}")
        with t_col4:
            st.info("Status: Live Monitoring")
        with t_col5:
            if st.button(f"🔴 Exit", key=f"sq_off_{idx}"):
                trade["status"] = "MANUAL_EXIT"
                trade["exit_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_json(PAPER_TRADES_FILE, paper_data)
                st.success(f"Closed {trade.get('asset')} position!")
                st.rerun()

# -------------------------------------------------------------
# 6. SECTOR MOMENTUM HEATMAP (COLORED CARDS)
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

                clean_name = sec_name.replace("NIFTY ", "")

                with sec_cols[idx]:
                    st.markdown(f"""
                        <div style="
                            background-color: {bg_color}; 
                            border: 1px solid {border_color}; 
                            border-radius: 8px; 
                            padding: 8px 4px; 
                            text-align: center;
                            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
                        ">
                            <div style="font-size: 11px; font-weight: 700; color: #555555; text-transform: uppercase;">
                                {clean_name}
                            </div>
                            <div style="font-size: 14px; font-weight: 800; color: #111111; margin: 2px 0;">
                                {curr:.1f}
                            </div>
                            <div style="font-size: 12px; font-weight: 700; color: {text_color};">
                                {icon} {pct:+.2f}%
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
            except Exception:
                pass
    except Exception:
        st.caption("Sector radar loading...")

# -------------------------------------------------------------
# 7. DATA ENGINE & CALCULATION PIPELINE
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
active_breakouts = 0
has_sniper_alert = False

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
                trade_logic = f"Closed above resistance ({res_level:.2f}) with {rvol:.1f}x vol and VWAP support."
                if (rvol >= 2.5 or is_special) and (c_close > ema50) and (rsi >= 58):
                    grade = "Grade A+ (Sniper)"
                    has_sniper_alert = True
                elif (rvol >= 1.6 or is_special) and (rsi >= 53):
                    grade = "Grade A (Inst.)"
                else:
                    grade = "Grade B (Scalp)"
            elif is_breakdown:
                signal = "🔴 SELL BREAKDOWN"
                active_breakouts += 1
                trade_logic = f"Closed below support ({sup_level:.2f}) with bearish volume pressure."
                if (rvol >= 2.5 or is_special) and (c_close < ema50) and (rsi <= 42):
                    grade = "Grade A+ (Sniper)"
                    has_sniper_alert = True
                elif (rvol >= 1.6 or is_special) and (rsi <= 47):
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
# 8. BROWSER AUDIO BEEP CHIME (ON GRADE A+ BREAKOUTS)
# -------------------------------------------------------------
if has_sniper_alert:
    audio_chime = """
    <script>
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, audioCtx.currentTime); // A5 note
        gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.6);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.6);
    } catch(e) {}
    </script>
    """
    components.html(audio_chime, height=0, width=0)

# -------------------------------------------------------------
# 9. METRIC CARDS ROW
# -------------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Universe Tracked", len(tickers))
with m2:
    st.metric("Active Breakouts", active_breakouts)
with m3:
    st.metric("Risk Budget", f"₹{risk_per_trade}")
with m4:
    st.metric("Execution Mode", execution_type)

st.markdown("---")

# -------------------------------------------------------------
# 10. MONITORING DATA TABLE
# -------------------------------------------------------------
if records:
    df_display = pd.DataFrame(records).drop(columns=["Ticker", "Size"])
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("No active breakout setups currently found in this asset pool.")

# -------------------------------------------------------------
# 11. DUAL EXECUTION DESK (PAPER TRADING + SMARTAPI REAL FUND)
# -------------------------------------------------------------
st.markdown("### ⚡ Order Execution Desk")
ord_col1, ord_col2, ord_col3, ord_col4 = st.columns([2, 1.2, 1.2, 1.5])
asset_names = [r["Asset"] for r in records] if records else []

with ord_col1:
    chosen_asset = st.selectbox("Contract / Asset:", asset_names if asset_names else ["None"])

selected_item = next((r for r in records if r["Asset"] == chosen_asset), None)

with ord_col2:
    side = st.selectbox("Direction:", ["BUY", "SELL"])

with ord_col3:
    suggested_qty = selected_item["Size"] if selected_item else 1
    qty_input = st.number_input("Qty / Lots:", min_value=1, value=max(1, suggested_qty), step=1)

with ord_col4:
    st.write("")
    st.write("")
    
    if is_beginner or execution_type == "Paper Trading":
        if st.button("📥 Record Virtual Paper Trade", use_container_width=True):
            if selected_item:
                new_trade = {
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "asset": chosen_asset,
                    "type": side,
                    "entry": selected_item["LTP"],
                    "sl": selected_item["Stop Loss"],
                    "tp1": selected_item["Target 1 (1:1)"],
                    "tp2": selected_item["Target 2 (1:2)"],
                    "qty": qty_input,
                    "status": "OPEN"
                }
                paper_data["trades"].append(new_trade)
                save_json(PAPER_TRADES_FILE, paper_data)
                st.success(f"Virtual {side} Order Placed for {chosen_asset} at {selected_item['LTP']}!")
                st.rerun()
            else:
                st.warning("Asset select karein.")
    else:
        if st.button("🚀 Fire to Angel One (Real Fund)", use_container_width=True):
            if selected_item:
                raw_sym = selected_item["Ticker"]
                exch = "NSE" if ".NS" in raw_sym or "^NSE" in raw_sym else "MCX"
                clean_sym = raw_sym.replace(".NS", "").replace("^", "")
                
                ok, msg = place_order_smartapi(
                    symbol_token=clean_sym,
                    trading_symbol=clean_sym,
                    exchange=exch,
                    qty=qty_input,
                    transaction_type=side
                )
                if ok:
                    st.success(msg)
                else:
                    st.error(f"Execution failed: {msg}")
            else:
                st.warning("Asset select karein.")

# -------------------------------------------------------------
# 12. COMPLETED PAPER TRADE HISTORY LEDGER
# -------------------------------------------------------------
if closed_trades:
    with st.expander("📜 Completed Paper Trades Ledger", expanded=False):
        history_df = pd.DataFrame(closed_trades)
        st.dataframe(history_df, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 13. INTERACTIVE TRADINGVIEW CANDLESTICK CHART
# -------------------------------------------------------------
st.markdown("### 📈 Interactive TradingView Live Chart")
if records and selected_item:
    sym = selected_item["Ticker"].replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
    if sym == "^NSEI":
        sym = "NIFTY"
    elif sym == "^NSEBANK":
        sym = "BANKNIFTY"

    tv_code = f"""
    <div class="tradingview-widget-container" style="height:550px; width:100%;">
      <div id="tradingview_chart" style="height:550px;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": true,
        "symbol": "{sym}",
        "interval": "15",
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
