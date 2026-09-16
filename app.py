import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import urllib.parse
import urllib.request
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Pro Market Scanner", layout="centered")

# --- Telegram Alert Credentials ---
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_ID = "1527960238"

# Duplicate alert cache in session
if "sent_alerts" not in st.session_state:
    st.session_state.sent_alerts = set()

def send_telegram_alert(message, asset_key):
    if asset_key in st.session_state.sent_alerts:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=5)
        st.session_state.sent_alerts.add(asset_key)
    except Exception:
        pass

# CSS to lock layout for mobile screens
st.markdown("""
<style>
    .block-container {
        padding-top: 0.8rem;
        padding-bottom: 1rem;
        padding-left: 0.2rem;
        padding-right: 0.2rem;
    }
    .custom-table {
        width: 100% !important;
        border-collapse: collapse;
        font-size: 11px;
        margin-top: 8px;
    }
    .custom-table th {
        background-color: #1e293b;
        color: #ffffff;
        font-weight: 600;
        text-align: center;
        padding: 6px 2px;
        border: 1px solid #334155;
    }
    .custom-table td {
        text-align: center;
        padding: 5px 2px;
        border: 1px solid #cbd5e1;
        vertical-align: middle;
    }
    .chart-link {
        color: #0284c7;
        text-decoration: none;
        font-weight: bold;
    }
    .badge-strong {
        background-color: #16a34a;
        color: white;
        padding: 2px 3px;
        border-radius: 3px;
        font-weight: bold;
        font-size: 9px;
    }
    .badge-breakout {
        background-color: #ea580c;
        color: white;
        padding: 2px 3px;
        border-radius: 3px;
        font-weight: bold;
        font-size: 9px;
    }
    .badge-vol {
        background-color: #2563eb;
        color: white;
        padding: 2px 3px;
        border-radius: 3px;
        font-weight: bold;
        font-size: 9px;
    }
    .badge-watch {
        color: #64748b;
        font-size: 9px;
    }
</style>
""", unsafe_allow_html=True)

st.subheader("⚡ Pro Market Scanner")

# Controls row
c1, c2 = st.columns([1.2, 1])
with c1:
    market_choice = st.selectbox(
        "Market:",
        ["Indian Stocks (NSE)", "US Stocks (NASDAQ/NYSE)", "Forex (Currencies)", "Crypto"]
    )
with c2:
    auto_refresh = st.checkbox("Auto Refresh (60s)", value=False)
    if auto_refresh:
        st_autorefresh(interval=60000, key="datarefresh")

# Position sizing risk input
col_risk, col_flt = st.columns([1, 1])
with col_risk:
    max_risk = st.number_input("Risk Limit per Trade (₹/$):", min_value=100, value=1000, step=100)
with col_flt:
    filter_active = st.checkbox("Sirf Breakouts 🔥", value=False)

if market_choice == "Indian Stocks (NSE)":
    currency = "₹"
    tv_prefix = "NSE"
    WATCHLIST = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "BHARTIARTL.NS", "ITC.NS", "LT.NS", "TATAMOTORS.NS", "SBIN.NS",
        "ADANIENT.NS", "SUNPHARMA.NS", "BAJFINANCE.NS", "TITAN.NS", "TATASTEEL.NS"
    ]
elif market_choice == "US Stocks (NASDAQ/NYSE)":
    currency = "$"
    tv_prefix = "NASDAQ"
    WATCHLIST = [
        "AAPL", "NVDA", "TSLA", "MSFT", "AMZN",
        "META", "GOOGL", "AMD", "NFLX", "INTC"
    ]
elif market_choice == "Forex (Currencies)":
    currency = ""
    tv_prefix = "FX"
    WATCHLIST = [
        "USDINR=X", "EURUSD=X", "GBPUSD=X", "USDJPY=X", 
        "AUDUSD=X", "USDCAD=X", "USDCHF=X", "EURINR=X", 
        "GBPINR=X", "JPYINR=X"
    ]
else:
    currency = "$"
    tv_prefix = "BINANCE"
    WATCHLIST = [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "DOGE-USD"
    ]

def fetch_pro_analysis(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df.empty or len(df) < 50:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        rsi_series = ta.momentum.rsi(close, window=14)
        atr_series = ta.volatility.average_true_range(high, low, close, window=14)
        vol_sma_series = volume.rolling(window=20).mean()
        ema_50 = ta.trend.ema_indicator(close, window=50)

        # Volatility Squeeze (Bollinger Band inside Keltner Channel)
        bb_upper = ta.volatility.bollinger_hband(close, window=20, window_dev=2)
        bb_lower = ta.volatility.bollinger_lband(close, window=20, window_dev=2)
        kc_upper = ema_50 + (1.5 * atr_series)
        kc_lower = ema_50 - (1.5 * atr_series)

        ltp = float(close.iloc[-1])
        curr_rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0
        curr_atr = float(atr_series.iloc[-1]) if not atr_series.empty else (ltp * 0.015)
        curr_vol = float(volume.iloc[-1]) if not volume.empty else 0
        avg_vol = float(vol_sma_series.iloc[-1]) if not vol_sma_series.empty else 1
        curr_ema50 = float(ema_50.iloc[-1]) if not ema_50.empty else ltp

        recent_high = float(high.iloc[-21:-1].max())

        is_breakout = ltp > recent_high
        is_volume_spike = curr_vol > (1.5 * avg_vol) if avg_vol > 0 else False
        is_trend_bullish = ltp > curr_ema50
        is_squeeze = (float(bb_upper.iloc[-1]) < float(kc_upper.iloc[-1])) and (float(bb_lower.iloc[-1]) > float(kc_lower.iloc[-1]))

        signal = "WATCH"
        if is_breakout and is_volume_spike and is_trend_bullish:
            signal = "🚀 STRONG"
        elif is_breakout:
            signal = "🔥 BREAKOUT"
        elif is_squeeze and is_trend_bullish:
            signal = "⚡ SQUEEZE"
        elif is_volume_spike:
            signal = "⚡ VOL SURGE"

        dec = 4 if "=X" in ticker else 2
        buy_level = round(ltp, dec)
        stop_loss = round(ltp - curr_atr, dec)
        target = round(ltp + (2 * curr_atr), dec)

        # Dynamic position sizing
        risk_per_share = curr_atr if curr_atr > 0 else (ltp * 0.015)
        shares_qty = int(max_risk / risk_per_share) if risk_per_share > 0 else 1

        clean_symbol = ticker.replace(".NS", "").replace("=X", "")
        tv_symbol = clean_symbol if "=X" not in ticker else clean_symbol.replace("INR", "USD")
        tv_url = f"https://www.tradingview.com/chart/?symbol={tv_prefix}:{tv_symbol}"

        return {
            "Asset": clean_symbol,
            "ChartURL": tv_url,
            "Buy": buy_level,
            "SL": stop_loss,
            "TP": target,
            "Qty": max(shares_qty, 1),
            "RSI": round(curr_rsi, 1),
            "Signal": signal
        }
    except Exception:
        return None

with st.spinner("Analyzing market..."):
    results = []
    for sym in WATCHLIST:
        data = fetch_pro_analysis(sym)
        if data:
            results.append(data)
            if data["Signal"] in ["🚀 STRONG", "🔥 BREAKOUT", "⚡ SQUEEZE", "⚡ VOL SURGE"]:
                alert_text = (
                    f"🚨 Pro Alert Triggered!\n"
                    f"📈 Asset: {data['Asset']}\n"
                    f"🎯 Signal: {data['Signal']}\n"
                    f"💵 Buy: {currency}{data['Buy']}\n"
                    f"🛑 SL: {currency}{data['SL']}\n"
                    f"🏆 TP: {currency}{data['TP']}\n"
                    f"📦 Position Size: {data['Qty']} shares\n"
                    f"📊 RSI: {data['RSI']}"
                )
                send_telegram_alert(alert_text, f"{data['Asset']}_{data['Signal']}")

if results:
    display_list = [r for r in results if r["Signal"] != "WATCH"] if filter_active else results

    if display_list:
        html = '<table class="custom-table">'
        html += f'<thead><tr><th>Asset</th><th>Buy</th><th>SL</th><th>TP</th><th>Qty</th><th>RSI</th><th>Signal</th></tr></thead><tbody>'
        
        for row in display_list:
            sig = row["Signal"]
            if sig == "🚀 STRONG":
                sig_html = f'<span class="badge-strong">{sig}</span>'
            elif sig == "🔥 BREAKOUT":
                sig_html = f'<span class="badge-breakout">{sig}</span>'
            elif sig in ["⚡ VOL SURGE", "⚡ SQUEEZE"]:
                sig_html = f'<span class="badge-vol">{sig}</span>'
            else:
                sig_html = f'<span class="badge-watch">{sig}</span>'

            html += f'<tr>'
            html += f'<td><a class="chart-link" href="{row["ChartURL"]}" target="_blank">{row["Asset"]} ↗️</a></td>'
            html += f'<td>{row["Buy"]}</td>'
            html += f'<td style="color:#ef4444;">{row["SL"]}</td>'
            html += f'<td style="color:#16a34a;">{row["TP"]}</td>'
            html += f'<td><b>{row["Qty"]}</b></td>'
            html += f'<td>{row["RSI"]}</td>'
            html += f'<td>{sig_html}</td>'
            html += f'</tr>'

        html += '</tbody></table>'
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.info("Abhi koi breakout signal nahi mila.")
else:
    st.warning("Data load nahi ho saka.")
