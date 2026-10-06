import os
import json
import urllib.request
import urllib.parse
import pandas as pd
import numpy as np
import yfinance as yf
import ta
from datetime import datetime, timezone, timedelta

# -------------------------------------------------------------
# 1. TIMEZONE & CONFIGURATION
# -------------------------------------------------------------
def get_ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

ist_now = get_ist_now()
today_date_str = ist_now.strftime("%Y-%m-%d")
time_str = ist_now.strftime("%I:%M %p IST")
cur_mins = ist_now.hour * 60 + ist_now.minute

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1527960238")

# -------------------------------------------------------------
# 2. SENT ALERTS DEDUPLICATION (PREVENTS SPAM)
# -------------------------------------------------------------
SENT_ALERTS_FILE = "sent_alerts.json"

def load_sent_alerts():
    if os.path.exists(SENT_ALERTS_FILE):
        try:
            with open(SENT_ALERTS_FILE, "r") as f:
                data = json.load(f)
                # Purane din ke alerts reset karein
                if data.get("date") == today_date_str:
                    return data
        except Exception:
            pass
    return {"date": today_date_str, "sent": []}

def save_sent_alerts(data):
    try:
        with open(SENT_ALERTS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

sent_alerts_tracker = load_sent_alerts()

def send_telegram_msg(msg_text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing in environment variables.")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg_text,
            "parse_mode": "HTML"
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=12) as response:
            return response.status == 200
    except Exception as e:
        print(f"Telegram dispatch error: {e}")
        return False

# -------------------------------------------------------------
# 3. LIVE MARKET HEARTBEAT CHECK (ZERO-LEAK HOLIDAY ENGINE)
# -------------------------------------------------------------
def is_nse_active_today():
    # Monday=0, Sunday=6
    if ist_now.weekday() >= 5:
        return False
    # NSE Trading Hours: 9:15 AM to 3:30 PM (555 to 930 mins)
    if not (555 <= cur_mins <= 930):
        return False
    try:
        bench_df = yf.download("^NSEI", period="2d", interval="1d", progress=False)
        if not bench_df.empty:
            last_date = str(bench_df.dropna().index[-1].date())
            return (last_date == today_date_str)
        return False
    except Exception:
        return False

nse_live = is_nse_active_today()
print(f"[{time_str}] NSE Live Status: {nse_live}")

# -------------------------------------------------------------
# 4. ASSET UNIVERSES (FULL ORIGINAL 80+ ASSETS)
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

# Active Universe Selection
scan_universe = []
if nse_live:
    scan_universe.extend(NSE_EQUITIES)

scan_universe.extend(COMMODITIES_AND_FOREX)
scan_universe.extend(CRYPTO_ASSETS)

# US Market Hours: 7:00 PM to 1:30 AM IST (1140 to 1440 or 0 to 90 mins)
if (cur_mins >= 1140) or (cur_mins <= 90):
    if ist_now.weekday() < 5:
        scan_universe.extend(US_EQUITIES)

# -------------------------------------------------------------
# 5. SCANNER EXECUTION & TELEGRAM DISPATCH
# -------------------------------------------------------------
def scan_and_alert():
    if not scan_universe:
        print("No active markets to scan at this hour.")
        return

    print(f"Scanning {len(scan_universe)} assets...")
    try:
        raw = yf.download(scan_universe, period="1mo", interval="1h", group_by="ticker", progress=False)
    except Exception as e:
        print(f"Download failed: {e}")
        return

    alerts_triggered = 0

    for ticker in scan_universe:
        try:
            df = raw[ticker] if len(scan_universe) > 1 else raw
            df = df.dropna()

            if len(df) < 20:
                continue

            # Candle timestamp freshness check
            is_indian = (".NS" in ticker or "^NSE" in ticker)
            last_date = str(df.index[-1].date())
            if is_indian and (last_date != today_date_str or not nse_live):
                continue

            # Deduplication: Ek asset ka alert ek din me sirf 1 baar aayega
            if ticker in sent_alerts_tracker["sent"]:
                continue

            c_close = float(df['Close'].iloc[-1])
            c_open = float(df['Open'].iloc[-1])
            c_vol = float(df['Volume'].iloc[-1])

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

            # Breakout logic with RSI protection (50 to 68)
            is_buy = (c_close > res_level) and (c_close > c_open) and (c_close > ema20) and (50 <= rsi <= 68)
            is_sell = (c_close < sup_level) and (c_close < c_open) and (c_close < ema20) and (32 <= rsi <= 50)

            if not (is_buy or is_sell):
                continue

            # Strict 1:2 Minimum Risk-Reward
            sl_dist = 1.0 * atr
            if is_buy:
                signal_type = "🟢 SWING BUY BREAKOUT"
                sl = c_close - sl_dist
                tp1 = c_close + (2.0 * sl_dist)
                tp2 = c_close + (3.5 * sl_dist)
                level = res_level
            else:
                signal_type = "🔴 SWING SELL BREAKDOWN"
                sl = c_close + sl_dist
                tp1 = c_close - (2.0 * sl_dist)
                tp2 = c_close - (3.5 * sl_dist)
                level = sup_level

            is_fx = any(fx in ticker for fx in ["=", "USD", "^"])
            dec = "%.4f" if is_fx else "%.2f"
            clean_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("^", "").replace("-USD", ""))

            msg = (
                f"⚡ <b>NEW SWING SETUP TRIGGERED</b>\n\n"
                f"📊 <b>Asset:</b> {clean_name} ({ticker})\n"
                f"🎯 <b>Signal:</b> {signal_type}\n"
                f"🕒 <b>Time:</b> {time_str}\n\n"
                f"💵 <b>CMP:</b> {dec % c_close}\n"
                f"🧱 <b>Breakout Level:</b> {dec % level}\n"
                f"🛑 <b>Stop Loss (1x ATR):</b> {dec % sl}\n"
                f"🎯 <b>Target 1 (1:2 Min):</b> {dec % tp1}\n"
                f"🚀 <b>Target 2 (1:3.5 Ext):</b> {dec % tp2}\n\n"
                f"📈 <b>RSI:</b> {rsi:.1f} | <b>Vol:</b> {'Liquid' if is_special else f'{rvol:.2f}x'}\n"
                f"💡 <i>Strategy: Wait for minor pullback or enter at CMP with disciplined risk.</i>"
            )

            if send_telegram_msg(msg):
                sent_alerts_tracker["sent"].append(ticker)
                save_sent_alerts(sent_alerts_tracker)
                alerts_triggered += 1
                print(f"Alert sent for {clean_name}")

        except Exception as e:
            continue

    print(f"Scan complete. Total alerts sent: {alerts_triggered}")

if __name__ == "__main__":
    scan_and_alert()
