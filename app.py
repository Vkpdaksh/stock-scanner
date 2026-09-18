import os
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import yfinance as yf
import ta
import pyotp
from datetime import datetime, timezone, timedelta

# Page Configuration
st.set_page_config(
    page_title="Institutional Trading Terminal",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom Styling
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric {
        background-color: #1a1c24;
        border-radius: 8px;
        padding: 10px;
        border: 1px solid #2d3139;
    }
    .sector-card {
        border-radius: 6px;
        padding: 10px;
        margin: 4px;
        text-align: center;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# ANGEL ONE SMARTAPI SETUP & ORDER EXECUTION
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
        return False, "SmartAPI session not active. Check credentials."
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
        response = api.placeOrder(order_params)
        if response.get("status"):
            return True, f"Order placed successfully! ID: {response.get('data', {}).get('orderid')}"
        else:
            return False, response.get("message", "Order rejected by broker")
    except Exception as e:
        return False, str(e)

# -------------------------------------------------------------
# ASSET UNIVERSES & SECTOR REGISTRY
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
# TOP CONTROLS & HEADER
# -------------------------------------------------------------
st.title("⚡ Institutional Grade Trading Terminal")

col1, col2, col3 = st.columns([2, 1.5, 1])

with col1:
    selected_universe = st.selectbox(
        "Active Asset Universe:",
        list(MARKET_UNIVERSES.keys()),
        index=0
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
    auto_sync = st.checkbox("Auto-Sync (60s) 🔄", value=True)

# -------------------------------------------------------------
# SECTOR MOMENTUM HEATMAP
# -------------------------------------------------------------
with st.expander("📊 Live Sectoral Momentum Heatmap (NSE)", expanded=True):
    try:
        sector_tickers = list(SECTOR_INDICES.values())
        sec_data = yf.download(sector_tickers, period="2d", interval="15m", group_by='ticker', progress=False)
        cols = st.columns(len(SECTOR_INDICES))
        
        for idx, (sec_name, sec_sym) in enumerate(SECTOR_INDICES.items()):
            try:
                s_df = sec_data[sec_sym].dropna()
                curr = float(s_df['Close'].iloc[-1])
                prev = float(s_df['Close'].iloc[0])
                pct = ((curr - prev) / prev) * 100
                bg_color = "#1b5e20" if pct > 0.5 else ("#2e7d32" if pct > 0 else ("#b71c1c" if pct < -0.5 else "#c62828"))
                
                with cols[idx]:
                    st.markdown(f"""
                        <div style="background-color: {bg_color}; border-radius: 6px; padding: 8px; text-align: center;">
                            <div style="font-size: 11px; color: #cfd8dc;">{sec_name}</div>
                            <div style="font-size: 14px; font-weight: bold; color: white;">{pct:+.2f}%</div>
                        </div>
                    """, unsafe_allow_html=True)
            except Exception:
                pass
    except Exception:
        st.caption("Sector data fetching paused.")

# -------------------------------------------------------------
# DATA ENGINE & SCANNER
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
# METRICS & TABLE DISPLAY
# -------------------------------------------------------------
m_col1, m_col2, m_col3 = st.columns(3)
with m_col1:
    st.metric("Universe Tracked", len(tickers))
with m_col2:
    st.metric("Active Breakouts", active_breakouts)
with m_col3:
    st.metric("Selected Universe", selected_universe)

st.markdown("---")

if records:
    df_display = pd.DataFrame(records)
    st.dataframe(
        df_display.drop(columns=["Ticker", "Size"]),
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No active market data fetched for this universe.")

# -------------------------------------------------------------
# 1-CLICK ANGEL ONE SMARTAPI ORDER EXECUTION CONSOLE
# -------------------------------------------------------------
st.markdown("### ⚡ 1-Click SmartAPI Order Execution")
ord_col1, ord_col2, ord_col3, ord_col4 = st.columns([2, 1.5, 1.5, 1.5])

asset_names = [r["Asset"] for r in records] if records else []
with ord_col1:
    chosen_asset_name = st.selectbox("Select Asset to Trade:", asset_names if asset_names else ["None"])

chosen_record = next((r for r in records if r["Asset"] == chosen_asset_name), None)

with ord_col2:
    trade_side = st.selectbox("Order Type:", ["BUY", "SELL"])

with ord_col3:
    default_lot = chosen_record["Size"] if chosen_record else 1
    order_qty = st.number_input("Execution Quantity:", min_value=1, value=max(1, default_lot), step=1)

with ord_col4:
    st.write("")
    st.write("")
    if st.button("🚀 Fire Order in Angel One", use_container_width=True):
        if not chosen_record:
            st.warning("Select a valid asset first.")
        else:
            raw_sym = chosen_record["Ticker"]
            exch = "NSE" if ".NS" in raw_sym or "^NSE" in raw_sym else "MCX"
            clean_token = raw_sym.replace(".NS", "").replace("^", "")
            
            success, msg = place_order_smartapi(
                symbol_token=clean_token,
                trading_symbol=clean_token,
                exchange=exch,
                qty=order_qty,
                transaction_type=trade_side
            )
            if success:
                st.success(msg)
            else:
                st.error(f"Execution failed: {msg}")

# -------------------------------------------------------------
# INTERACTIVE TRADINGVIEW CHART WIDGET
# -------------------------------------------------------------
st.markdown("### 📈 Interactive TradingView Live Chart")
if records:
    clean_chart_symbol = chosen_record["Ticker"].replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
    if clean_chart_symbol == "^NSEI":
        clean_chart_symbol = "NIFTY"
    elif clean_chart_symbol == "^NSEBANK":
        clean_chart_symbol = "BANKNIFTY"

    tv_html = f"""
    <div class="tradingview-widget-container" style="height:550px; width:100%;">
      <div id="tradingview_chart" style="height:550px;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": true,
        "symbol": "{clean_chart_symbol}",
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
    components.html(tv_html, height=560)
