import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import urllib.parse
import urllib.request

st.set_page_config(page_title="Market Scanner", layout="centered")

# --- Telegram Alert Credentials ---
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_ID = "1527960238"

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

# CSS to strictly lock table width inside mobile screen
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        padding-left: 0.3rem;
        padding-right: 0.3rem;
    }
    .custom-table {
        width: 100% !important;
        border-collapse: collapse;
        font-size: 11px;
        margin-top: 10px;
    }
    .custom-table th {
        background-color: #f1f3f5;
        color: #111;
        font-weight: bold;
        text-align: center;
        padding: 6px 2px;
        border: 1px solid #dee2e6;
    }
    .custom-table td {
        text-align: center;
        padding: 6px 2px;
        border: 1px solid #dee2e6;
        vertical-align: middle;
    }
    .badge-strong {
        background-color: #28a745;
        color: white;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: bold;
        font-size: 10px;
    }
    .badge-breakout {
        background-color: #ff9800;
        color: white;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: bold;
        font-size: 10px;
    }
    .badge-vol {
        background-color: #007bff;
        color: white;
        padding: 2px 4px;
        border-radius: 3px;
        font-weight: bold;
        font-size: 10px;
    }
    .badge-watch {
        color: #6c757d;
        font-size: 10px;
    }
</style>
""", unsafe_allow_html=True)

st.subheader("⚡ Live Market Scanner")

market_choice = st.selectbox(
    "Market Chuniye:",
    ["Indian Stocks (NSE)", "US Stocks (NASDAQ/NYSE)", "Forex (Currencies)", "Crypto"]
)

if market_choice == "Indian Stocks (NSE)":
    currency = "₹"
    WATCHLIST = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "BHARTIARTL.NS", "ITC.NS", "LT.NS", "TATAMOTORS.NS", "SBIN.NS",
        "ADANIENT.NS", "SUNPHARMA.NS", "BAJFINANCE.NS", "TITAN.NS", "TATASTEEL.NS"
    ]
elif market_choice == "US Stocks (NASDAQ/NYSE)":
    currency = "$"
    WATCHLIST = [
        "AAPL", "NVDA", "TSLA", "MSFT", "AMZN",
        "META", "GOOGL", "AMD", "NFLX", "INTC"
    ]
elif market_choice == "Forex (Currencies)":
    currency = ""
    WATCHLIST = [
        "USDINR=X", "EURUSD=X", "GBPUSD=X", "USDJPY=X", 
        "AUDUSD=X", "USDCAD=X", "USDCHF=X", "EURINR=X", 
        "GBPINR=X", "JPYINR=X"
    ]
else:
    currency = "$"
    WATCHLIST = [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "DOGE-USD"
    ]

def fetch_analysis(ticker):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False)
        if df.empty or len(df) < 20:
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

        ltp = float(close.iloc[-1])
        curr_rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0
        curr_atr = float(atr_series.iloc[-1]) if not atr_series.empty else (ltp * 0.015)
        curr_vol = float(volume.iloc[-1]) if not volume.empty else 0
        avg_vol = float(vol_sma_series.iloc[-1]) if not vol_sma_series.empty else 1

        recent_high = float(high.iloc[-21:-1].max())

        is_breakout = ltp > recent_high
        is_volume_spike = curr_vol > (1.5 * avg_vol) if avg_vol > 0 else False

        signal = "WATCH"
        if is_breakout and is_volume_spike:
            signal = "🚀 STRONG"
        elif is_breakout:
            signal = "🔥 BREAKOUT"
        elif is_volume_spike:
            signal = "⚡ VOL SURGE"

        dec = 4 if "=X" in ticker else 2
        buy_level = round(ltp, dec)
        stop_loss = round(ltp - curr_atr, dec)
        target = round(ltp + (2 * curr_atr), dec)

        clean_symbol = ticker.replace(".NS", "").replace("=X", "")

        return {
            "Asset": clean_symbol,
            "Buy": buy_level,
            "SL": stop_loss,
            "TP": target,
            "RSI": round(curr_rsi, 1),
            "Signal": signal
        }
    except Exception:
        return None

col1, col2 = st.columns([1, 1])
with col1:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()
with col2:
    filter_active = st.checkbox("Sirf Breakouts 🔥", value=False)

with st.spinner("Scanning..."):
    results = []
    for sym in WATCHLIST:
        data = fetch_analysis(sym)
        if data:
            results.append(data)
            # Automatic alert for strong signals
            if data["Signal"] in ["🚀 STRONG", "🔥 BREAKOUT", "⚡ VOL SURGE"]:
                alert_text = (
                    f"🚨 Market Alert Triggered!\n"
                    f"📈 Asset: {data['Asset']}\n"
                    f"🎯 Signal: {data['Signal']}\n"
                    f"💵 Buy: {currency}{data['Buy']}\n"
                    f"🛑 SL: {currency}{data['SL']}\n"
                    f"🏆 TP: {currency}{data['TP']}\n"
                    f"📊 RSI: {data['RSI']}"
                )
                send_telegram_alert(alert_text)

if results:
    if filter_active:
        display_list = [r for r in results if r["Signal"] != "WATCH"]
    else:
        display_list = results

    if display_list:
        # Build strict mobile HTML table matching your exact sketch
        html = '<table class="custom-table">'
        html += f'<thead><tr><th>Asset</th><th>Buy ({currency})</th><th>SL</th><th>TP</th><th>RSI</th><th>Signal</th></tr></thead><tbody>'
        
        for row in display_list:
            sig = row["Signal"]
            if sig == "🚀 STRONG":
                sig_html = f'<span class="badge-strong">{sig}</span>'
            elif sig == "🔥 BREAKOUT":
                sig_html = f'<span class="badge-breakout">{sig}</span>'
            elif sig == "⚡ VOL SURGE":
                sig_html = f'<span class="badge-vol">{sig}</span>'
            else:
                sig_html = f'<span class="badge-watch">{sig}</span>'

            html += f'<tr>'
            html += f'<td><b>{row["Asset"]}</b></td>'
            html += f'<td>{row["Buy"]}</td>'
            html += f'<td style="color:#d9534f;">{row["SL"]}</td>'
            html += f'<td style="color:#28a745;">{row["TP"]}</td>'
            html += f'<td>{row["RSI"]}</td>'
            html += f'<td>{sig_html}</td>'
            html += f'</tr>'

        html += '</tbody></table>'
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.info("Abhi koi breakout signal nahi hai.")
else:
    st.warning("Data fetch nahi ho saka. Kripya Refresh karein.")
