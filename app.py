import os
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import yfinance as yf
import ta
from datetime import datetime, timezone, timedelta

# -------------------------------------------------------------
# 1. PAGE SETUP & INSTITUTIONAL DARK HEDGE-FUND UI THEME
# -------------------------------------------------------------
st.set_page_config(
    page_title="Terminal Pro | Institutional Desk",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for Bloomberg / TradingView Glassmorphism Style
st.markdown("""
<style>
    /* Global App Styling */
    .stApp {
        background-color: #0B0E14 !important;
        color: #D1D4DC !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* Hide Streamlit Native Chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Top Strip Header */
    .top-strip {
        background: linear-gradient(90deg, #131722 0%, #1E222D 100%);
        border: 1px solid #2A2E39;
        border-radius: 8px;
        padding: 10px 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 15px;
    }

    /* Metric Cards */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #151A24 0%, #1C2331 100%) !important;
        border: 1px solid #2B3548 !important;
        border-radius: 8px !important;
        padding: 12px 16px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.45);
    }
    [data-testid="stMetricValue"] {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 24px !important;
    }
    [data-testid="stMetricLabel"] {
        color: #787B86 !important;
        font-weight: 600 !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Dataframe Header Tweaks */
    thead tr th {
        background-color: #131722 !important;
        color: #848E9C !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }

    /* Buttons */
    .stButton>button {
        background: linear-gradient(135deg, #2962FF 0%, #1E53E5 100%) !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 8px 18px !important;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        background: linear-gradient(135deg, #1E53E5 0%, #1545C7 100%) !important;
        box-shadow: 0 0 10px rgba(41, 98, 255, 0.5) !important;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. SMARTAPI SESSION INITIALIZER
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
# 3. UNIVERSE & SECTOR DEFINITIONS
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
# 4. TOP INSTITUTIONAL STATUS BAR
# -------------------------------------------------------------
ist_now = get_ist_now()
time_str = ist_now.strftime("%I:%M:%S %p IST")

# Session Status
is_nse_open = (ist_now.weekday() < 5) and (
    (ist_now.hour == 9 and ist_now.minute >= 15) or 
    (10 <= ist_now.hour < 15) or 
    (ist_now.hour == 15 and ist_now.minute <= 30)
)
session_badge = "<span style='color: #00E676;'>● NSE OPEN</span>" if is_nse_open else "<span style='color: #FF5252;'>● NSE CLOSED</span>"

st.markdown(f"""
<div class="top-strip">
    <div style="font-size: 16px; font-weight: 700; color: #FFFFFF; letter-spacing: 0.5px;">
        🏛️ INSTITUTIONAL TRADING TERMINAL <span style="font-size: 11px; background-color: #2962FF; color: white; padding: 2px 6px; border-radius: 4px; margin-left: 6px;">PRO V3</span>
    </div>
    <div style="font-size: 13px; color: #B2B5BE;">
        {session_badge} &nbsp;|&nbsp; 🟢 LIVE FEED: <span style="color: #FFFFFF; font-weight: bold;">{time_str}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 5. CONTROL BAR & PARAMETERS
# -------------------------------------------------------------
col1, col2, col3 = st.columns([2, 1.5, 1])

with col1:
    selected_universe = st.selectbox(
        "ACTIVE ASSET UNIVERSE:",
        list(MARKET_UNIVERSES.keys()),
        index=0
    )

with col2:
    risk_per_trade = st.number_input(
        "MAX RISK POSITION (₹ / $):",
        min_value=100,
        max_value=50000,
        value=1500,
        step=100
    )

with col3:
    auto_sync = st.checkbox("Auto-Sync (60s) 🔄", value=True)

# -------------------------------------------------------------
# 6. SECTORAL MOMENTUM HEATMAP
# -------------------------------------------------------------
with st.expander("📊 LIVE SECTOR MOMENTUM HEATMAP (NSE)", expanded=True):
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
                bg = "#0A3B24" if pct > 0.4 else ("#11291F" if pct > 0 else ("#4A121A" if pct < -0.4 else "#2A1418"))
                txt_c = "#00E676" if pct >= 0 else "#FF5252"
                
                with sec_cols[idx]:
                    st.markdown(f"""
                        <div style="background-color: {bg}; border: 1px solid {txt_c}40; border-radius: 6px; padding: 6px; text-align: center;">
                            <div style="font-size: 10px; color: #9E9E9E; font-weight: 600;">{sec_name.replace('NIFTY ', '')}</div>
                            <div style="font-size: 13px; font-weight: 700; color: {txt_c};">{pct:+.2f}%</div>
                        </div>
                    """, unsafe_allow_html=True)
            except Exception:
                pass
    except Exception:
        st.caption("Sector radar loading...")

# -------------------------------------------------------------
# 7. DATA ENGINE & CALCULATION PIPELINE
# -------------------------------------------------------------
tickers = MARKET_UNIVERSES[selected_universe]

@st.cache_data(ttl=60)
def fetch_market_data(ticker_list):
    try:
        return yf.download(ticker_list, period="5d", interval="15m", group_by='ticker', progress=False)
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

            is_breakout = (c_close > res_level) and (c_close > c_open) and (c_close > ema20)
            is_breakdown = (c_close < sup_level) and (c_close < c_open) and (c_close < ema20)

            if is_breakout:
                signal = "🟢 BUY BREAKOUT"
                active_breakouts += 1
                if (rvol >= 2.5 or is_special) and (c_close > ema50) and (rsi >= 58):
                    grade = "Grade A+ (Sniper)"
                elif (rvol >= 1.6 or is_special) and (rsi >= 53):
                    grade = "Grade A (Inst.)"
                else:
                    grade = "Grade B (Scalp)"
            elif is_breakdown:
                signal = "🔴 SELL BREAKDOWN"
                active_breakouts += 1
                if (rvol >= 2.5 or is_special) and (c_close < ema50) and (rsi <= 42):
                    grade = "Grade A+ (Sniper)"
                elif (rvol >= 1.6 or is_special) and (rsi <= 47):
                    grade = "Grade A (Inst.)"
                else:
                    grade = "Grade B (Scalp)"
            else:
                signal = "⚪ CONSOLIDATION"
                grade = "Neutral"

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
                "Size": rec_size
            })
        except Exception:
            continue

# -------------------------------------------------------------
# 8. METRIC CARDS ROW
# -------------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("UNIVERSE TRACKED", len(tickers))
with m2:
    st.metric("ACTIVE SIGNALS", active_breakouts)
with m3:
    st.metric("RISK BUDGET", f"₹{risk_per_trade}")
with m4:
    st.metric("SYSTEM MODE", "SNIPER READY" if active_breakouts > 0 else "SCANNING")

st.write("")

# -------------------------------------------------------------
# 9. COLOR-CODED PRO DATA TABLE (PANDAS STYLER)
# -------------------------------------------------------------
def style_signal(val):
    if 'BUY' in str(val):
        return 'background-color: #064E3B; color: #34D399; font-weight: 700;'
    elif 'SELL' in str(val):
        return 'background-color: #7F1D1D; color: #F87171; font-weight: 700;'
    return 'color: #94A3B8;'

def style_grade(val):
    if 'Grade A+' in str(val):
        return 'background-color: #312E81; color: #A5B4FC; font-weight: 700; border: 1px solid #6366F1;'
    elif 'Grade A' in str(val):
        return 'color: #38BDF8; font-weight: 600;'
    return 'color: #64748B;'

if records:
    df_raw = pd.DataFrame(records)
    table_view = df_raw.drop(columns=["Ticker", "Size"])

    styled_table = (
        table_view.style
        .map(style_signal, subset=['Signal'])
        .map(style_grade, subset=['Setup Grade'])
        .format({
            "LTP": "{:.2f}",
            "Stop Loss": "{:.2f}",
            "Target 1 (1:1)": "{:.2f}",
            "Target 2 (1:2)": "{:.2f}",
            "RSI": "{:.1f}"
        })
    )

    st.dataframe(
        styled_table,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Searching for institutional footprints across feed...")

# -------------------------------------------------------------
# 10. 1-CLICK SMARTAPI ORDER EXECUTION CONSOLE
# -------------------------------------------------------------
st.markdown("### ⚡ 1-Click SmartAPI Order Desk")
with st.container():
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
        if st.button("🚀 FIRE TO ANGEL ONE", use_container_width=True):
            if not selected_item:
                st.warning("Select contract first.")
            else:
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
                    st.error(f"Failed: {msg}")

# -------------------------------------------------------------
# 11. EMBEDDED ADVANCED TRADINGVIEW CHART WIDGET
# -------------------------------------------------------------
st.markdown("### 📈 Interactive TradingView Candlestick Terminal")
if records and selected_item:
    sym = selected_item["Ticker"].replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
    if sym == "^NSEI":
        sym = "NIFTY"
    elif sym == "^NSEBANK":
        sym = "BANKNIFTY"

    tv_code = f"""
    <div class="tradingview-widget-container" style="height:540px; width:100%;">
      <div id="tradingview_chart" style="height:540px;"></div>
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
    components.html(tv_code, height=550)
