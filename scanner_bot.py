import os
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
import pandas as pd
import ta
import yfinance as yf

# -------------------------------------------------------------
# CREDENTIALS & STORAGE PATHS
# -------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_IDS = [
    "1527960238",         # Personal Chat
    "-1004352653406"       # Private Channel (Quant Move Alerts)
]

CACHE_FILE = "sent_alerts.json"
ACTIVE_TRADES_FILE = "active_trades.json"
DAILY_STATS_FILE = "daily_stats.json"

DEFAULT_RISK_PER_TRADE = 1000  # ₹1,000 reference risk allocation

# -------------------------------------------------------------
# WATCHLIST REGISTRY
# -------------------------------------------------------------
MARKET_CATEGORIES = {
    "🇮🇳 INDIAN EQUITIES (NSE)": [
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
    "🇺🇸 US EQUITIES (NASDAQ/NYSE)": [
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "NFLX", "PLTR",
        "AVGO", "SMCI", "ARM", "QCOM", "INTC", "MU", "PANW", "CRWD", "COIN", "MSTR"
    ],
    "🌍 FOREX & COMMODITIES": [
        "GC=F", "SI=F", "CL=F", "HG=F", "INR=X", "EURUSD=X", 
        "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"
    ],
    "🪙 CRYPTO (24x7)": [
        "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD",
        "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "SUI-USD"
    ]
}

NAME_MAP = {
    "GC=F": "XAUUSD (Gold Futures)",
    "SI=F": "XAGUSD (Silver Futures)",
    "CL=F": "CRUDE OIL (WTI)",
    "HG=F": "COPPER FUTURES",
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

def get_market_category(ticker):
    for cat, t_list in MARKET_CATEGORIES.items():
        if ticker in t_list:
            return cat
    return "🌐 GLOBAL MARKET"

# -------------------------------------------------------------
# FILE HELPERS
# -------------------------------------------------------------
def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(filepath, data):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def send_telegram(text_msg, buttons_data=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            payload = {
                "chat_id": chat_id,
                "text": text_msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": "true"
            }
            if buttons_data:
                payload["reply_markup"] = json.dumps({"inline_keyboard": buttons_data})
            
            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode(payload).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

def get_ist_time():
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=5, minutes=30)

# -------------------------------------------------------------
# ACTIVE TRADES MONITORING (EARLY EXIT + SL + TARGET 1 & 2)
# -------------------------------------------------------------
def monitor_active_trades(active_trades, daily_stats, today_str):
    if not active_trades:
        return {}

    updated_trades = {}
    tickers = list(active_trades.keys())
    
    try:
        data = yf.download(tickers, period="3d", interval="15m", group_by='ticker', progress=False)
    except Exception:
        return active_trades

    if "closed_trades" not in daily_stats:
        daily_stats["closed_trades"] = []

    for ticker, info in active_trades.items():
        try:
            df = data[ticker] if len(tickers) > 1 else data
            df = df.dropna()
            if df.empty or len(df) < 5:
                updated_trades[ticker] = info
                continue

            curr_price = float(df['Close'].iloc[-1])
            curr_low = float(df['Low'].iloc[-1])
            curr_high = float(df['High'].iloc[-1])
            
            entry_price = info["entry"]
            breakout_level = info.get("breakout_level", entry_price)
            sl_price = info["sl"]
            tp1_price = info["tp1"]
            tp2_price = info["tp2"]
            currency = info.get("currency", "")
            market_tag = info.get("market", "")
            display_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("-USD", ""))

            clean_sym = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
            tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
            buttons = [[{"text": "📊 Open TradingView", "url": tv_link}]]

            # ---------------------------------------------------------
            # 1. STOP-LOSS HIT (Worst Case Floor)
            # ---------------------------------------------------------
            if curr_low <= sl_price:
                msg = (
                    f"🛑 *STOP-LOSS HIT / EXIT ALERT*\n"
                    f"🏛️ *Market:* **{market_tag}**\n\n"
                    f"📉 *Asset:* **{display_name}**\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 4 if '=' in ticker else 2)}\n"
                    f"🛑 *SL Level Triggered:* {currency}{sl_price}\n"
                    f"💡 *Action:* **Exit immediately** to safeguard capital.\n\n"
                    f"⚠️ *Disclaimer:* Algorithmic notification for tracking purposes only."
                )
                send_telegram(msg, buttons)
                daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "SL"})
                continue  # Trade closed, remove from active

            # ---------------------------------------------------------
            # 2. EARLY REVERSAL EXIT (BEFORE SL HIT)
            # Agar price breakout level ke wapas andar gir jaye aur 2 candles sustain na kare
            # ---------------------------------------------------------
            c1 = float(df['Close'].iloc[-1])
            c2 = float(df['Close'].iloc[-2])
            if (c1 < breakout_level and c2 < breakout_level) and not info.get("tp1_hit", False):
                msg = (
                    f"⚠️ *EARLY REVERSAL DETECTED (EXIT BEFORE SL)*\n"
                    f"🏛️ *Market:* **{market_tag}**\n\n"
                    f"📉 *Asset:* **{display_name}**\n"
                    f"🔍 *Reason:* Price fell back inside base level ({currency}{breakout_level})\n"
                    f"💵 *Current LTP:* {currency}{round(curr_price, 4 if '=' in ticker else 2)} (Entry: {currency}{entry_price})\n"
                    f"💡 *Action:* **Exit near cost/minimal loss**. Breakout failed, do NOT wait for full SL hit.\n\n"
                    f"⚠️ *Disclaimer:* Risk management alert for algorithmic tracking."
                )
                send_telegram(msg, buttons)
                daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "EARLY_EXIT"})
                continue  # Trade invalidated early, save capital!

            # ---------------------------------------------------------
            # 3. TARGET 1 HIT (1:1 RRR - 50% Book & Trail SL to Entry)
            # ---------------------------------------------------------
            elif curr_high >= tp1_price and not info.get("tp1_hit", False):
                msg = (
                    f"🎯 *TARGET 1 (1:1) ACHIEVED!*\n"
                    f"🏛️ *Market:* **{market_tag}**\n\n"
                    f"🏆 *Asset:* **{display_name}**\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 4 if '=' in ticker else 2)} (Entry: {currency}{entry_price})\n"
                    f"🎯 *Target 1 Level:* {currency}{tp1_price}\n\n"
                    f"💡 *Recommended Action:*\n"
                    f"• **Book 50% Profit**\n"
                    f"• **Trail Stop-Loss to Entry/Cost** ({currency}{entry_price})\n"
                    f"• Hold remaining 50% for Final Target 2 ({currency}{tp2_price})\n\n"
                    f"⚠️ *Disclaimer:* Educational tracking notification."
                )
                send_telegram(msg, buttons)
                info["tp1_hit"] = True
                info["sl"] = entry_price  # Stop-loss shifted to cost (Risk-Free Trade)
                updated_trades[ticker] = info
                daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "TP1"})

            # ---------------------------------------------------------
            # 4. FINAL TARGET 2 HIT (1:2 RRR - Full Exit)
            # ---------------------------------------------------------
            elif curr_high >= tp2_price:
                msg = (
                    f"🏆 *FINAL TARGET 2 (1:2) ACHIEVED!*\n"
                    f"🏛️ *Market:* **{market_tag}**\n\n"
                    f"🚀 *Asset:* **{display_name}**\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 4 if '=' in ticker else 2)}\n"
                    f"🎯 *Final Target:* {currency}{tp2_price}\n\n"
                    f"💡 *Recommended Action:* **Close full position** and lock complete 1:2 profit!\n\n"
                    f"⚠️ *Disclaimer:* Educational tracking notification."
                )
                send_telegram(msg, buttons)
                daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "TP2"})
                continue  # Full exit, remove from active

            else:
                updated_trades[ticker] = info
        except Exception:
            updated_trades[ticker] = info

    return updated_trades

# -------------------------------------------------------------
# BATCH SCANNER WITH 1:1 AND 1:2 RRR
# -------------------------------------------------------------
def run_batch_market_scan(sent_cache, active_trades, ist_now):
    batch_size = 35
    all_tickers = []
    for cat_list in MARKET_CATEGORIES.values():
        all_tickers.extend(cat_list)

    scan_candidates = [t for t in all_tickers if t not in sent_cache and t not in active_trades]
    
    curr_min = ist_now.minute
    start_window_min = (curr_min // 15) * 15
    start_time_str = ist_now.replace(minute=start_window_min).strftime("%I:%M %p")
    end_time = ist_now.replace(minute=start_window_min) + timedelta(minutes=15)
    end_time_str = end_time.strftime("%I:%M %p IST")
    entry_window_label = f"{start_time_str} - {end_time_str}"

    for i in range(0, len(scan_candidates), batch_size):
        batch = scan_candidates[i:i + batch_size]
        try:
            data_15m = yf.download(batch, period="5d", interval="15m", group_by='ticker', progress=False)
            
            for ticker in batch:
                try:
                    df_15m = data_15m[ticker] if len(batch) > 1 else data_15m
                    df_15m = df_15m.dropna()
                    if len(df_15m) < 25:
                        continue

                    c_close = float(df_15m['Close'].iloc[-1])
                    c_open = float(df_15m['Open'].iloc[-1])
                    c_vol = float(df_15m['Volume'].iloc[-1])

                    prev_window = df_15m.iloc[-25:-1]
                    res_level = float(prev_window['High'].max())
                    avg_vol = float(prev_window['Volume'].mean()) or 1.0

                    if c_close <= res_level or c_close <= c_open:
                        continue

                    is_forex_or_comm = ("=" in ticker or "^" in ticker)
                    rvol = (c_vol / avg_vol) if avg_vol > 0 else 1.0
                    
                    if not is_forex_or_comm and rvol < 1.5:
                        continue

                    atr_series = ta.volatility.average_true_range(df_15m['High'], df_15m['Low'], df_15m['Close'], window=14)
                    atr = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else (c_close * 0.01)

                    rsi_series = ta.momentum.rsi(df_15m['Close'], window=14)
                    rsi = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else 50.0

                    if rsi < 48 or rsi > 80:
                        continue

                    # 1:1 for TP1, 1:2 for TP2
                    sl_dist = 1.0 * atr
                    sl = round(c_close - sl_dist, 4 if is_forex_or_comm else 2)
                    tp1 = round(c_close + sl_dist, 4 if is_forex_or_comm else 2)
                    tp2 = round(c_close + (2.0 * sl_dist), 4 if is_forex_or_comm else 2)

                    market_tag = get_market_category(ticker)
                    display_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("-USD", ""))
                    currency = "₹" if ".NS" in ticker else ("$" if ("-USD" in ticker or "=F" in ticker) else "")

                    risk_unit = max(round(c_close - sl, 4 if is_forex_or_comm else 2), 0.0001)
                    rec_qty = max(1, int(DEFAULT_RISK_PER_TRADE / risk_unit)) if currency == "₹" else max(1, int(50 / risk_unit))

                    clean_sym = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
                    tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
                    screener_link = f"https://www.screener.in/company/{clean_sym}/" if ".NS" in ticker else f"https://finviz.com/quote.ashx?t={clean_sym}"

                    msg = (
                        f"🎯 *NEW BREAKOUT ALERT*\n"
                        f"🏛️ *Market:* **{market_tag}**\n\n"
                        f"📈 *Asset:* **{display_name}**\n"
                        f"⏰ *Entry Time Window:* `{entry_window_label}` (On Candle Confirmation)\n"
                        f"💵 *Reference Entry Zone:* {currency}{round(c_close, 4 if is_forex_or_comm else 2)}\n"
                        f"🛑 *Stop-Loss (SL):* {currency}{sl}\n"
                        f"🎯 *Target 1 (50% Profit Book):* {currency}{tp1} (1:1)\n"
                        f"🏆 *Target 2 (Final Exit):* {currency}{tp2} (1:2)\n\n"
                        f"⚖️ *Risk : Reward:* **1 : 2.0 (Max)**\n"
                        f"🧮 *Reference Sizing:* ~**{rec_qty} Units** (~₹1,000 risk cap)\n"
                        f"📊 *15m RSI:* {round(rsi, 1)} | *RVol:* {round(rvol, 2)}x ✅\n\n"
                        f"⚠️ *Disclaimer:* For algorithmic & educational research only. Not financial or investment advice. Always manage personal risk."
                    )

                    buttons = [
                        [
                            {"text": "📊 Open TradingView", "url": tv_link},
                            {"text": "🔍 Deep Analysis", "url": screener_link}
                        ]
                    ]

                    send_telegram(msg, buttons)
                    
                    sent_cache.add(ticker)
                    active_trades[ticker] = {
                        "entry": round(c_close, 4 if is_forex_or_comm else 2),
                        "breakout_level": round(res_level, 4 if is_forex_or_comm else 2),
                        "sl": sl,
                        "tp1": tp1,
                        "tp2": tp2,
                        "currency": currency,
                        "market": market_tag,
                        "tp1_hit": False,
                        "date": ist_now.strftime("%Y-%m-%d")
                    }
                    print(f"Alert sent & tracked: {display_name}")
                except Exception:
                    continue

        except Exception:
            pass

        time.sleep(1)

# -------------------------------------------------------------
# MAIN ENGINE
# -------------------------------------------------------------
if __name__ == "__main__":
    ist_now = get_ist_time()
    today_str = ist_now.strftime("%Y-%m-%d")

    # SLEEP GUARD: Raat 11:00 PM - Subah 8:00 AM IST tak exit
    if ist_now.hour >= 23 or ist_now.hour < 8:
        print(f"[{ist_now.strftime('%H:%M IST')}] Night cutoff active (11:00 PM - 8:00 AM). Exiting clean.")
        exit(0)

    cache_data = load_json(CACHE_FILE, {"date": today_str, "tickers": []})
    if cache_data.get("date") != today_str:
        sent_cache = set()
    else:
        sent_cache = set(cache_data.get("tickers", []))

    active_trades = load_json(ACTIVE_TRADES_FILE, {})
    daily_stats = load_json(DAILY_STATS_FILE, {})

    # 1. MONITOR ACTIVE TRADES (EARLY EXIT + SL + TARGET 1 & 2)
    active_trades = monitor_active_trades(active_trades, daily_stats, today_str)

    # 2. RUN BATCH SCAN FOR NEW TRADES
    run_batch_market_scan(sent_cache, active_trades, ist_now)

    # 3. SAVE STATE
    save_json(CACHE_FILE, {"date": today_str, "tickers": list(sent_cache)})
    save_json(ACTIVE_TRADES_FILE, active_trades)
    save_json(DAILY_STATS_FILE, daily_stats)
