import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Institutional Trading Terminal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    .main {background-color: #0b0e14;}
    div[data-testid="stMetricValue"] {font-size: 22px; font-weight: 700;}
    .reportview-container .main .block-container {padding-top: 1.5rem;}
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Institutional Grade Trading Terminal")

# -------------------------------------------------------------
# COMPLETE COMPREHENSIVE WATCHLISTS
# -------------------------------------------------------------
WATCHLISTS = {
    "⚡ Index Options (Nifty & Bank Nifty)": [
        "^NSEI", "^NSEBANK", "NIFTY_FIN_SERVICE.NS"
    ],
    "Indian Momentum Leaders (60+ Stocks)": [
        # Nifty 50 Bluechips & Banking
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS",
        "KOTAKBANK.NS", "LT.NS", "BHARTIARTL.NS", "ITC.NS", "HINDUNILVR.NS", "TATAMOTORS.NS", "MARUTI.NS",
        "M&M.NS", "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
        "TITAN.NS", "BAJFINANCE.NS", "ADANIENT.NS", "ADANIPORTS.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS",
        
        # High-Beta Midcaps, Defence, Railways & Energy Leaders
        "SUZLON.NS", "IREDA.NS", "RVNL.NS", "IRFC.NS", "IRCON.NS", "RAILTEL.NS", "MAZDOCK.NS", "COCHINSHIP.NS",
        "HAL.NS", "BEL.NS", "BDL.NS", "BHEL.NS", "HUDCO.NS", "NBCC.NS", "SAIL.NS", "NMDC.NS", "NATIONALUM.NS",
        "BSE.NS", "CDSL.NS", "ANGELONE.NS", "MCX.NS", "TATATECH.NS", "TRENT.NS", "ZOMATO.NS", "JIOFIN.NS",
        "DIXON.NS", "POLYCAB.NS", "KEI.NS", "KALYANKJIL.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "PERSISTENT.NS",
        "COFORGE.NS", "DLF.NS", "LODHA.NS", "AUROPHARMA.NS", "LUPIN.NS", "EXIDEIND.NS", "ASHOKLEY.NS"
    ],
    "US Tech Giants (Nasdaq Leaders)": [
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "NFLX", "PLTR",
        "AVGO", "SMCI", "ARM", "QCOM", "INTC", "MU", "PANW", "CRWD", "COIN", "MSTR"
    ],
    "Forex & Commodities": [
        # Gold, Silver & Energy
        "GC=F",      # XAUUSD Gold Futures
        "SI=F",      # XAGUSD Silver Futures
        "CL=F",      # Crude Oil
        "HG=F",      # Copper
        # 8 Major Global Currencies
        "INR=X",     # USD/INR
        "EURUSD=X",  # EUR/USD
        "GBPUSD=X",  # GBP/USD
        "USDJPY=X",  # USD/JPY
        "AUDUSD=X",  # AUD/USD
        "USDCAD=X",  # USD/CAD
        "USDCHF=X",  # USD/CHF
        "NZDUSD=X"   # NZD/USD
    ],
    "Major Indices (Global & Sectors)": [
        "^NSEI", "^NSEBANK", "^CNXIT", "^CNXAUTO", "^CNXMETAL", "^IXIC", "^GSPC", "^DJI"
    ],
    "Crypto (24x7)": [
        "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD",
        "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "SUI-USD"
    ]
}

NAME_MAP = {
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "NIFTY_FIN_SERVICE.NS": "FIN NIFTY",
    "^CNXIT": "NIFTY IT",
    "^CNXAUTO": "NIFTY AUTO",
    "^CNXMETAL": "NIFTY METAL",
    "^IXIC": "NASDAQ 100",
    "^GSPC": "S&P 500",
    "^DJI": "DOW JONES",
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
    "NZDUSD=X": "NZD/USD"
}

# -------------------------------------------------------------
# TOP CONTROLS & RISK DESK
# -------------------------------------------------------------
ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4 = st.columns([2, 1.2, 1, 1])

with ctrl_c1:
    market_choice = st.selectbox("Active Asset Universe:", list(WATCHLISTS.keys()))

with ctrl_c2:
    risk_budget = st.number_input("Max Risk Per Position (₹ / $):", min_value=500, max_value=50000, value=1500, step=500)

with ctrl_c3:
    sound_alert = st.checkbox("Audio Chime 🔔", value=True)

with ctrl_c4:
    auto_refresh = st.checkbox("Auto-Sync (60s) ⏱️", value=True)

selected_tickers = WATCHLISTS[market_choice]

# -------------------------------------------------------------
# OPTION STRIKE ENGINE
# -------------------------------------------------------------
def get_atm_strike(index_name, spot_price):
    if "NIFTY 50" in index_name:
        step, lot_size = 50, 25
    elif "BANK NIFTY" in index_name:
        step, lot_size = 100, 15
    else:
        step, lot_size = 50, 40
    atm_strike = int(round(spot_price / step) * step)
    return atm_strike, lot_size

# -------------------------------------------------------------
# INSTITUTIONAL BATCH SCAN ENGINE
# -------------------------------------------------------------
@st.cache_data(ttl=30)
def execute_institutional_scan(tickers, market_type, risk_amount):
    results = []
    # Batch download 15m candles
    data_15m = yf.download(tickers, period="5d", interval="15m", group_by='ticker', progress=False)

    for ticker in tickers:
        try:
            df_15m = data_15m[ticker] if len(tickers) > 1 else data_15m
            df_15m = df_15m.dropna()
            if len(df_15m) < 25:
                continue

            c_close = float(df_15m['Close'].iloc[-1])
            c_open = float(df_15m['Open'].iloc[-1])
            prev_window = df_15m.iloc[-25:-1]
            res_level = float(prev_window['High'].max())
            sup_level = float(prev_window['Low'].min())
            
            vol = float(df_15m['Volume'].iloc[-1])
            avg_vol = float(prev_window['Volume'].mean()) or 1.0
            rvol = round(vol / avg_vol, 2) if avg_vol > 0 else 1.0

            # Volatility & Momentum Indicators
            atr_s = ta.volatility.average_true_range(df_15m['High'], df_15m['Low'], df_15m['Close'], window=14)
            atr = float(atr_s.dropna().iloc[-1]) if not atr_s.dropna().empty else (c_close * 0.005)

            rsi_s = ta.momentum.rsi(df_15m['Close'], window=14)
            rsi = round(float(rsi_s.dropna().iloc[-1]), 1) if not rsi_s.dropna().empty else 50.0

            ema20_s = ta.trend.ema_indicator(df_15m['Close'], window=20)
            ema20 = float(ema20_s.dropna().iloc[-1])

            # Multi-Timeframe / Liquidity Checks
            is_index_or_fx = ("^" in ticker or "=" in ticker or "Index" in market_type)
            vol_passed = True if is_index_or_fx else (rvol >= 1.4)
            trend_passed = c_close >= ema20

            bullish_breakout = (c_close > res_level) and (c_close > c_open) and vol_passed and trend_passed
            bearish_breakdown = (c_close < sup_level) and (c_close < c_open) and vol_passed and (c_close < ema20)

            name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", ""))

            if "Index Options" in market_type:
                atm_strike, lot_size = get_atm_strike(name, c_close)
                opt_sl_pts = max(round(atr * 0.4, 1), 15.0)
                opt_tp_pts = round(opt_sl_pts * 1.8, 1)
                risk_lot = opt_sl_pts * lot_size
                rec_lots = max(1, int(risk_amount / risk_lot))

                if bullish_breakout:
                    signal = f"🟢 BUY {atm_strike} CE"
                    score = "💎 Grade A+"
                    prio = 0
                elif bearish_breakdown:
                    signal = f"🔴 BUY {atm_strike} PE"
                    score = "💎 Grade A+"
                    prio = 0
                else:
                    signal = "⚪ CONSOLIDATION"
                    score = "Neutral"
                    prio = 1

                results.append({
                    "Priority": prio,
                    "Asset": name,
                    "Signal": signal,
                    "Setup Grade": score,
                    "Spot Price": round(c_close, 2),
                    "Opt SL": f"-{opt_sl_pts} pts",
                    "Opt Target": f"+{opt_tp_pts} pts",
                    "Lot Allocation": f"{rec_lots} Lot ({rec_lots * lot_size} Qty)",
                    "Capital At Risk": f"₹{int(risk_lot * rec_lots)}",
                    "RSI": rsi,
                    "Ticker_Raw": ticker,
                    "Is_Actionable": prio == 0
                })
            else:
                sl = round(c_close - (1.1 * atr), 2 if "=" not in ticker else 4)
                tp = round(c_close + (1.65 * atr), 2 if "=" not in ticker else 4)
                curr_sym = "₹" if ".NS" in ticker else ("$" if market_type in ["US Tech Giants (Nasdaq Leaders)", "Crypto (24x7)"] else "")

                if bullish_breakout:
                    signal = "🟢 STRONG BUY"
                    score = "💎 Grade A+" if (rvol >= 2.0 or is_index_or_fx) else "🔥 Grade A"
                    prio = 0
                else:
                    signal = "⚪ CONSOLIDATION"
                    score = "Neutral"
                    prio = 1

                risk_per_unit = max(round(c_close - sl, 4), 0.0001)
                alloc_qty = max(1, int(risk_amount / risk_per_unit))

                results.append({
                    "Priority": prio,
                    "Asset": name,
                    "Signal": signal,
                    "Setup Grade": score,
                    "LTP": f"{curr_sym}{round(c_close, 2 if '=' not in ticker else 4)}",
                    "Stop Loss": f"{curr_sym}{sl}",
                    "Target (1:1.5)": f"{curr_sym}{tp}",
                    "RVol": f"{rvol}x 🔥" if rvol >= 2.0 else (f"{rvol}x" if not is_index_or_fx else "Liquid"),
                    "RSI": rsi,
                    "Recommended Size": f"{alloc_qty} Units",
                    "Ticker_Raw": ticker,
                    "Is_Actionable": prio == 0
                })
        except Exception:
            continue

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values(by=["Priority"]).drop(columns=["Priority"])
    return df

with st.spinner("Analyzing institutional price action & volume across all assets..."):
    df_terminal = execute_institutional_scan(selected_tickers, market_choice, risk_budget)

if not df_terminal.empty:
    actionable_count = int(df_terminal["Is_Actionable"].sum())

    if sound_alert and actionable_count > 0:
        st.markdown("""
            <audio autoplay>
                <source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" type="audio/mpeg">
            </audio>
        """, unsafe_allow_html=True)

    # Top Metric Bar
    stat1, stat2, stat3 = st.columns(3)
    stat1.metric("Universe Tracked", len(df_terminal))
    stat2.metric("Active Breakouts", actionable_count, delta="Execution Ready" if actionable_count > 0 else "Neutral")
    stat3.metric("Selected Segment", market_choice)

    # Clean Table Render
    display_table = df_terminal.drop(columns=["Ticker_Raw", "Is_Actionable"])
    st.dataframe(display_table, use_container_width=True, height=380)

    # -------------------------------------------------------------
    # EMBEDDED INTERACTIVE CANDLESTICK CHART DESK
    # -------------------------------------------------------------
    st.markdown("---")
    chart_col1, chart_col2 = st.columns([1.5, 3.5])

    with chart_col1:
        st.subheader("🔍 Deep Chart Inspection")
        asset_names = df_terminal["Asset"].tolist()
        selected_asset = st.selectbox("Inspect Asset Candles:", asset_names)
        raw_ticker = df_terminal.loc[df_terminal["Asset"] == selected_asset, "Ticker_Raw"].iloc[0]

        st.info(f"Viewing real-time chart for **{selected_asset}** with 20 EMA, 50 EMA and RSI Momentum indicator.")

    with chart_col2:
        try:
            candle_df = yf.download(raw_ticker, period="5d", interval="15m", progress=False)
            if isinstance(candle_df.columns, pd.MultiIndex):
                candle_df.columns = [c[0] for c in candle_df.columns]
            candle_df = candle_df.dropna()

            candle_df['EMA20'] = ta.trend.ema_indicator(candle_df['Close'], window=20)
            candle_df['EMA50'] = ta.trend.ema_indicator(candle_df['Close'], window=50)
            candle_df['RSI'] = ta.momentum.rsi(candle_df['Close'], window=14)

            # Interactive Plotly Subplots
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.75, 0.25])

            fig.add_trace(go.Candlestick(
                x=candle_df.index,
                open=candle_df['Open'], high=candle_df['High'],
                low=candle_df['Low'], close=candle_df['Close'],
                name="Candles"
            ), row=1, col=1)

            fig.add_trace(go.Scatter(
                x=candle_df.index, y=candle_df['EMA20'],
                line=dict(color='#00e5ff', width=1.5),
                name="20 EMA"
            ), row=1, col=1)

            fig.add_trace(go.Scatter(
                x=candle_df.index, y=candle_df['EMA50'],
                line=dict(color='#ffab00', width=1.5),
                name="50 EMA"
            ), row=1, col=1)

            fig.add_trace(go.Scatter(
                x=candle_df.index, y=candle_df['RSI'],
                line=dict(color='#e040fb', width=1.5),
                name="RSI (14)"
            ), row=2, col=1)

            fig.add_hline(y=70, line_dash="dash", line_color="gray", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="gray", row=2, col=1)

            fig.update_layout(
                height=520,
                margin=dict(l=10, r=10, t=25, b=10),
                template="plotly_dark",
                xaxis_rangeslider_visible=False,
                showlegend=True
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.warning("Chart render ho raha hai, thoda intezar karein.")
else:
    st.info("Market data syncing. Please wait a moment.")

# Auto refresh handler
if auto_refresh:
    time.sleep(60)
    st.rerun()
