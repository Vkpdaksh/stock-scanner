import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
import ta

# -------------------------------------------------------------
# 1. CONFIGURATION & CONSTANTS
# -------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_ID = "1527960238"

ALERT_CACHE_FILE = "recent_alerts.json"
EOD_FLAG_FILE = "eod_sent_flag.json"
PAPER_TRADES_FILE = "paper_trades.json"

def get_ist_now():
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)

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

def send_telegram(text_msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text_msg,
            "parse_mode": "HTML"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram Send Error: {e}")
        return False

# -------------------------------------------------------------
# 2. WATCHLISTS & ASSETS UNIVERSE (ALL 80 STOCKS + FOREX + US)
# -------------------------------------------------------------
NSE_EQUITIES = [
    # Benchmark Indices
    "^NSEI", "^NSEBANK",
    # Banking & Financials
    "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", 
    "INDUSINDBK.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "SBILIFE.NS", "JIOFIN.NS", 
    "ANGELONE.NS", "BSE.NS", "CDSL.NS", "MCX.NS",
    # IT & Tech
    "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "LTIM.NS", 
    "PERSISTENT.NS", "COFORGE.NS", "TATATECH.NS",
    # Auto & EV
    "TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "EICHERMOT.NS", "ASHOKLEY.NS", "EXIDEIND.NS",
    # Energy & Green Infra
    "RELIANCE.NS", "ONGC.NS", "COALINDIA.NS", "NTPC.NS", "POWERGRID.NS", 
    "TATAPOWER.NS", "ADANIGREEN.NS", "SUZLON.NS", "IREDA.NS",
    # Defence & PSU Engineering
    "HAL.NS", "BEL.NS", "BDL.NS", "BHEL.NS", "MAZDOCK.NS", "COCHINSHIP.NS",
    # Railways & PSU Infrastructure
    "RVNL.NS", "IRFC.NS", "IRCON.NS", "RAILTEL.NS", "HUDCO.NS", "NBCC.NS",
    # Metals & Mining
    "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "SAIL.NS", "NMDC.NS", "NATIONALUM.NS",
    # Infrastructure, Capital Goods & Real Estate
    "LT.NS", "ULTRACEMCO.NS", "GRASIM.NS", "DLF.NS", "LODHA.NS",
    # FMCG, Consumption & Retail
    "ITC.NS", "HINDUNILVR.NS", "ASIANPAINT.NS", "TATACONSUM.NS", "TITAN.NS", 
    "TRENT.NS", "ZOMATO.NS", "KALYANKJIL.NS", "DIXON.NS", "POLYCAB.NS", "KEI.NS",
    # Pharma & Healthcare
    "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "AUROPHARMA.NS", "LUPIN.NS",
    # Conglomerates & Ports
    "BHARTIARTL.NS", "ADANIENT.NS", "ADANIPORTS.NS"
]

COMMODITIES_AND_FOREX = [
    # Commodities
    "GC=F", "SI=F", "CL=F", "HG=F", "NG=F",
    # Major Currencies
    "INR=X", "EURUSD=X", "GBPUSD=X", "USDJPY=X", 
    "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X",
    # Cross Currency Pairs
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
# 3. 1-HOUR TRADE ALERT COOLDOWN (NO DUPLICATE SPAM)
# -------------------------------------------------------------
def should_send_trade_alert(ticker_symbol, ist_time):
    """
    Ek hi trade ka alert baar-baar nahi bhejega.
    Agar dubara setup banta hai toh kam se kam 60 minutes ka gap hona zaroori hai.
    """
    cache = load_json(ALERT_CACHE_FILE, {})
    last_sent_str = cache.get(ticker_symbol)
    
    if last_sent_str:
        try:
            last_sent_time = datetime.strptime(last_sent_str, "%Y-%m-%d %H:%M:%S")
            time_diff = (ist_time.replace(tzinfo=None) - last_sent_time).total_seconds() / 60.0
            if time_diff < 60:
                print(f"Skipping duplicate alert for {ticker_symbol} (Cooldown active: {time_diff:.1f}/60 mins)")
                return False
        except Exception:
            pass

    cache[ticker_symbol] = ist_time.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    save_json(ALERT_CACHE_FILE, cache)
    return True

# -------------------------------------------------------------
# 4. TIMED SESSION EOD DISPATCHER (NSE 4 PM | FOREX 9:30 PM | US 11:30 PM)
# -------------------------------------------------------------
def check_and_send_eod(ist_time):
    cur_mins = ist_time.hour * 60 + ist_time.minute
    today_str = ist_time.strftime("%Y-%m-%d")
    flag_data = load_json(EOD_FLAG_FILE, {})

    target_session = None
    # 4:00 PM to 4:45 PM IST -> NSE EOD
    if 960 <= cur_mins <= 1005:
        target_session = "NSE"
    # 9:30 PM to 10:15 PM IST -> FOREX/COMMODITY EOD
    elif 1290 <= cur_mins <= 1335:
        target_session = "FOREX"
    # 11:30 PM to 11:59 PM IST -> US EQUITIES EOD
    elif 1410 <= cur_mins <= 1439:
        target_session = "US"

    if not target_session:
        return

    session_flag_key = f"{today_str}_{target_session}"
    if flag_data.get(session_flag_key):
        return  # Aaj is session ka report pehle hi deliver ho chuka hai

    p_data = load_json(PAPER_TRADES_FILE, {"trades": [], "balance": 10000.0})
    all_trades = p_data.get("trades", [])
    today_trades = [t for t in all_trades if str(t.get("date", "")).startswith(today_str)]
    today_closed = [t for t in today_trades if t.get("status") != "OPEN"]

    tp_hits = len([t for t in today_closed if t.get("status") == "TARGET_HIT"])
    sl_hits = len([t for t in today_closed if t.get("status") == "SL_HIT"])
    today_pnl = sum([float(t.get("pnl", 0.0)) for t in today_closed])
    win_rate = (tp_hits / len(today_closed) * 100) if today_closed else 0.0
    sign = "+" if today_pnl >= 0 else ""

    session_titles = {
        "NSE": "🏛️ INDIAN EQUITIES (NSE) SESSION CLOSE",
        "FOREX": "🌍 FOREX & COMMODITIES TRANSITION REPORT",
        "US": "🇺🇸 US EQUITIES (WALL STREET) EOD REPORT"
    }

    eod_msg = (
        f"📊 <b>{session_titles[target_session]}</b>\n"
        f"📅 Date: {today_str} | 🕒 Time: {ist_time.strftime('%I:%M %p IST')}\n\n"
        f"🔢 Total Swing Setups Today: {len(today_trades)}\n"
        f"🎯 Targets Hit: {tp_hits} ✅\n"
        f"🛑 Stop-Loss Hits: {sl_hits} ❌\n"
        f"📈 Session Win-Rate: {win_rate:.1f}%\n\n"
        f"💵 Today's Closed P&L: <b>₹{sign}{today_pnl:,.2f}</b>\n"
        f"⚡ Currently Open Trades: <b>{len([t for t in all_trades if t.get('status') == 'OPEN'])}</b>\n\n"
        f"💡 Status: Scheduled Session EOD Verified."
    )

    if send_telegram(eod_msg):
        flag_data[session_flag_key] = True
        save_json(EOD_FLAG_FILE, flag_data)
        print(f"EOD Report for {target_session} delivered successfully.")

# -------------------------------------------------------------
# 5. MAIN SCANNER ENGINE (SWING 1-HOUR INTERVAL)
# -------------------------------------------------------------
def run_scanner():
    ist_now = get_ist_now()
    cur_mins = ist_now.hour * 60 + ist_now.minute
    print(f"\n=======================================================")
    print(f"Running Scanner at {ist_now.strftime('%Y-%m-%d %I:%M:%S %p IST')}")
    print(f"=======================================================")

    # 1. Market Routing based on IST time
    if 555 <= cur_mins <= 930:
        active_universe = NSE_EQUITIES
        market_label = "INDIAN EQUITIES (NSE)"
    elif 930 < cur_mins <= 1290:
        active_universe = COMMODITIES_AND_FOREX
        market_label = "FOREX & COMMODITIES"
    else:
        active_universe = US_EQUITIES
        market_label = "US EQUITIES (NASDAQ/NYSE)"

    print(f"Active Session: {market_label} ({len(active_universe)} Assets)")

    # 2. Download 1-Month of 1-Hour candles for Swing Scanning
    try:
        raw_data = yf.download(active_universe, period="1mo", interval="1h", group_by='ticker', progress=False)
    except Exception as e:
        print(f"Failed to fetch market data: {e}")
        raw_data = None

    if raw_data is not None:
        for ticker in active_universe:
            try:
                df = raw_data[ticker] if len(active_universe) > 1 else raw_data
                df = df.dropna()
                if len(df) < 20:
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

                # Swing Breakout / Breakdown Logic
                is_breakout = (c_close > res_level) and (c_close > c_open) and (c_close > ema20)
                is_breakdown = (c_close < sup_level) and (c_close < c_open) and (c_close < ema20)

                if not (is_breakout or is_breakdown):
                    continue

                display_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("^", "").replace("-USD", ""))
                decimals = 4 if (is_special and ("=" in ticker or "USD" in ticker)) else 2
                dec_fmt = "{:." + str(decimals) + "f}"

                sl_dist = 1.5 * atr
                if is_breakout:
                    signal = "🟢 SWING BUY BREAKOUT"
                    sl = c_close - sl_dist
                    target_1 = c_close + (1.5 * sl_dist)
                    target_2 = c_close + (3.0 * sl_dist)
                    level_name = "Resistance"
                    break_val = res_level
                    if (rvol >= 1.5 or is_special) and (c_close > ema50) and (rsi >= 55):
                        grade = "Grade A+ (Institutional)"
                    else:
                        grade = "Grade A (Swing)"
                else:
                    signal = "🔴 SWING SELL BREAKDOWN"
                    sl = c_close + sl_dist
                    target_1 = c_close - (1.5 * sl_dist)
                    target_2 = c_close - (3.0 * sl_dist)
                    level_name = "Support"
                    break_val = sup_level
                    if (rvol >= 1.5 or is_special) and (c_close < ema50) and (rsi <= 45):
                        grade = "Grade A+ (Institutional)"
                    else:
                        grade = "Grade A (Swing)"

                # Check 1-Hour Cooldown Filter
                if should_send_trade_alert(ticker, ist_now):
                    rvol_text = "High/Liquid" if is_special else f"{rvol:.2f}x"
                    alert_text = (
                        f"🚨 <b>{signal}</b>\n\n"
                        f"📌 <b>Asset:</b> {display_name} ({ticker})\n"
                        f"🏆 <b>Setup:</b> {grade}\n"
                        f"⏱️ <b>Timeframe:</b> 1-Hour Swing Candle\n\n"
                        f"💰 <b>LTP:</b> {dec_fmt.format(c_close)}\n"
                        f"🧱 <b>{level_name}:</b> {dec_fmt.format(break_val)}\n"
                        f"🛑 <b>Stop-Loss:</b> {dec_fmt.format(sl)}\n"
                        f"🎯 <b>Target 1 (1:1.5):</b> {dec_fmt.format(target_1)}\n"
                        f"🎯 <b>Target 2 (1:3):</b> {dec_fmt.format(target_2)}\n\n"
                        f"📊 <b>RSI:</b> {rsi:.1f} | <b>RVol:</b> {rvol_text}\n"
                        f"🕒 <b>Trigger Time:</b> {ist_now.strftime('%I:%M %p IST')}\n"
                        f"🔒 <b>Cooldown:</b> 60 mins active (No duplicate spam)"
                    )
                    send_telegram(alert_text)
                    print(f"Dispatched Swing Alert for {ticker} successfully!")
            except Exception as e:
                continue

    # 3. Check and Dispatch Session-Specific EOD Report
    check_and_send_eod(ist_now)

if __name__ == "__main__":
    run_scanner()
