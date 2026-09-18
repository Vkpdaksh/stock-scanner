import os
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
import ta
import yfinance as yf
import pyotp
import requests
import matplotlib
matplotlib.use('Agg')  # Headless mode for server execution
import matplotlib.pyplot as plt

# -------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# -------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_IDS = [
    "1527960238",         # Personal Chat
    "-1004352653406"       # Private Channel
]

CACHE_FILE = "sent_alerts.json"
ACTIVE_TRADES_FILE = "active_trades.json"
DAILY_STATS_FILE = "daily_stats.json"

DEFAULT_RISK_PER_TRADE = 1000       # Standard INR risk per trade
DAILY_MAX_LOSS_LIMIT = 2500         # Loss Limit for Sniper Activation

ANGEL_API_KEY = os.environ.get("ANGEL_API_KEY", "")
ANGEL_CLIENT_ID = os.environ.get("ANGEL_CLIENT_ID", "")
ANGEL_MPIN = os.environ.get("ANGEL_MPIN", "")
ANGEL_TOTP_KEY = os.environ.get("ANGEL_TOTP_KEY", "")

# -------------------------------------------------------------
# ANGEL ONE SMARTAPI SESSION INITIALIZER
# -------------------------------------------------------------
smart_api_client = None

def init_smart_api():
    global smart_api_client
    if not (ANGEL_API_KEY and ANGEL_CLIENT_ID and ANGEL_MPIN and ANGEL_TOTP_KEY):
        print("[SmartAPI] Credentials not found in environment. Running standard feeds.")
        return None
    try:
        from SmartApi import SmartConnect
        totp = pyotp.TOTP(ANGEL_TOTP_KEY).now()
        smart_api = SmartConnect(api_key=ANGEL_API_KEY)
        session_data = smart_api.generateSession(ANGEL_CLIENT_ID, ANGEL_MPIN, totp)
        if session_data.get("status"):
            print(f"[SmartAPI] Successfully authenticated for {ANGEL_CLIENT_ID}!")
            smart_api_client = smart_api
            return smart_api
        else:
            print(f"[SmartAPI] Auth failed: {session_data.get('message')}")
            return None
    except Exception as e:
        print(f"[SmartAPI] Exception during auth: {e}")
        return None

# -------------------------------------------------------------
# WATCHLIST REGISTRY
# -------------------------------------------------------------
INDEX_OPTION_TICKERS = ["^NSEI", "^NSEBANK"]

MARKET_CATEGORIES = {
    "⚡ INDEX OPTIONS (INTRADAY)": INDEX_OPTION_TICKERS,
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
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "GC=F": "XAUUSD (Gold)",
    "SI=F": "XAGUSD (Silver)",
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

def get_atm_option_details(index_ticker, spot_price):
    step = 50 if index_ticker == "^NSEI" else 100
    lot_size = 25 if index_ticker == "^NSEI" else 15
    atm_strike = int(round(spot_price / step) * step)
    return atm_strike, lot_size

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

def get_ist_time():
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=5, minutes=30)

def calculate_vwap(df):
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    vol = df['Volume'].replace(0, 1)
    return (typical_price * vol).cumsum() / vol.cumsum()

def get_market_vix():
    try:
        vix_df = yf.download("^INDIAVIX", period="2d", interval="15m", progress=False)
        if not vix_df.empty:
            return float(vix_df['Close'].dropna().iloc[-1])
    except Exception:
        pass
    return 14.5

def calculate_chandelier_exit(df, period=22, mult=3.0):
    atr = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=period)
    highest_high = df['High'].rolling(window=period).max()
    long_stop = highest_high - (mult * atr)
    return float(long_stop.dropna().iloc[-1]) if not long_stop.dropna().empty else float(df['Low'].iloc[-1])

# -------------------------------------------------------------
# VISUAL CHART GENERATOR (MATPLOTLIB)
# -------------------------------------------------------------
def generate_chart_snapshot(df, ticker, display_name, entry, sl, tp1, tp2):
    chart_path = f"/tmp/{ticker.replace('^', '').replace('=', '').replace(':', '')}_chart.png"
    try:
        sub_df = df.iloc[-35:].copy()
        fig, ax = plt.subplots(figsize=(9, 4.8), dpi=120)
        fig.patch.set_facecolor('#131722')
        ax.set_facecolor('#131722')

        # Draw Candlesticks
        for idx, (t, row) in enumerate(sub_df.iterrows()):
            color = '#26a69a' if row['Close'] >= row['Open'] else '#ef5350'
            ax.vlines(x=idx, ymin=row['Low'], ymax=row['High'], color=color, linewidth=1.2)
            body_bottom = min(row['Open'], row['Close'])
            body_top = max(row['Open'], row['Close'])
            body_height = max(body_top - body_bottom, (row['High'] - row['Low']) * 0.05)
            ax.bar(x=idx, height=body_height, bottom=body_bottom, color=color, width=0.6)

        # Plot Institutional Target & SL Lines
        ax.axhline(entry, color='#29b6f6', linestyle='--', linewidth=1.5, label=f'Entry ({entry})')
        ax.axhline(sl, color='#f44336', linestyle='--', linewidth=1.5, label=f'SL ({sl})')
        ax.axhline(tp1, color='#81c784', linestyle=':', linewidth=1.4, label=f'TP1 ({tp1})')
        ax.axhline(tp2, color='#4caf50', linestyle='-', linewidth=1.8, label=f'TP2 ({tp2})')

        ax.set_title(f"{display_name} - 15m Institutional Breakout", color='#ffffff', fontsize=13, fontweight='bold', pad=10)
        ax.tick_params(colors='#b2b5be', labelsize=8)
        ax.grid(True, linestyle=':', alpha=0.25, color='#787b86')
        ax.legend(loc='upper left', facecolor='#1e222d', edgecolor='#363c4e', labelcolor='#ffffff', fontsize=8)
        
        plt.tight_layout()
        plt.savefig(chart_path, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        return chart_path
    except Exception as e:
        print(f"Chart error: {e}")
        return None

# -------------------------------------------------------------
# TELEGRAM DISPATCHER (TEXT & PHOTO)
# -------------------------------------------------------------
def send_telegram(text_msg, buttons_data=None, chart_img_path=None):
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            if chart_img_path and os.path.exists(chart_img_path):
                # Send Photo with Caption
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                payload = {
                    "chat_id": chat_id,
                    "caption": text_msg,
                    "parse_mode": "Markdown"
                }
                if buttons_data:
                    payload["reply_markup"] = json.dumps({"inline_keyboard": buttons_data})
                
                with open(chart_img_path, 'rb') as img_f:
                    requests.post(url, data=payload, files={"photo": img_f}, timeout=15)
            else:
                # Send Text Message
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
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
        except Exception as e:
            print(f"Telegram dispatch error: {e}")

    # Remove temporary chart image after sending
    if chart_img_path and os.path.exists(chart_img_path):
        try:
            os.remove(chart_img_path)
        except Exception:
            pass

# -------------------------------------------------------------
# ACTIVE TRADES MONITORING
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
    if "net_loss_today" not in daily_stats:
        daily_stats["net_loss_today"] = 0

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
            is_pe = info.get("is_pe", False)
            display_name = info.get("display_name", NAME_MAP.get(ticker, ticker.replace(".NS", "")))
            trade_grade = info.get("grade", "A")

            clean_sym = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
            tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
            buttons = [[{"text": "📊 Open TradingView", "url": tv_link}]]

            # LONG / CE TRADES
            if not is_pe:
                if curr_low <= sl_price:
                    msg = (
                        f"🛑 *STOP-LOSS HIT / EXIT ALERT*\n"
                        f"🏷️ *Quality:* `{trade_grade}` | 🏛️ *Market:* **{market_tag}**\n\n"
                        f"📉 *Asset:* **{display_name}**\n"
                        f"💵 *Trigger:* {currency}{round(curr_price, 2)} (SL: {currency}{sl_price})\n"
                        f"💡 *Action:* **Exit position** to preserve capital.\n\n"
                        f"⚠️ *Disclaimer:* Algorithmic position tracking."
                    )
                    send_telegram(msg, buttons)
                    daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "SL"})
                    daily_stats["net_loss_today"] += DEFAULT_RISK_PER_TRADE
                    continue

                c1, c2 = float(df['Close'].iloc[-1]), float(df['Close'].iloc[-2])
                if (c1 < breakout_level and c2 < breakout_level) and not info.get("tp1_hit", False):
                    msg = (
                        f"⚠️ *EARLY REVERSAL DETECTED (EXIT BEFORE SL)*\n"
                        f"🏷️ *Quality:* `{trade_grade}` | 🏛️ *Market:* **{market_tag}**\n\n"
                        f"📉 *Asset:* **{display_name}**\n"
                        f"🔍 *Reason:* Fell back below breakout support ({currency}{breakout_level})\n"
                        f"💵 *LTP:* {currency}{round(curr_price, 2)} (Entry: {currency}{entry_price})\n"
                        f"💡 *Action:* **Exit near cost / minimal risk**.\n\n"
                        f"⚠️ *Disclaimer:* Algorithmic risk control alert."
                    )
                    send_telegram(msg, buttons)
                    daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "EARLY_EXIT"})
                    daily_stats["net_loss_today"] += int(DEFAULT_RISK_PER_TRADE * 0.3)
                    continue

                elif curr_high >= tp1_price and not info.get("tp1_hit", False):
                    chandelier_sl = calculate_chandelier_exit(df)
                    trail_level = max(entry_price, round(chandelier_sl, 2))
                    msg = (
                        f"🎯 *TARGET 1 (1:1 RRR) ACHIEVED!*\n"
                        f"🏷️ *Quality:* `{trade_grade}` | 🏛️ *Market:* **{market_tag}**\n\n"
                        f"🏆 *Asset:* **{display_name}**\n"
                        f"💵 *LTP:* {currency}{round(curr_price, 2)} (Entry: {currency}{entry_price})\n"
                        f"🎯 *Target 1 Level:* {currency}{tp1_price}\n\n"
                        f"💡 *Action:*\n"
                        f"• **Book 50% Profit**\n"
                        f"• **Trail SL to Cost/Chandelier:** {currency}{trail_level}\n"
                        f"• Hold remainder for Target 2 ({currency}{tp2_price})\n\n"
                        f"⚠️ *Disclaimer:* Educational tracking."
                    )
                    send_telegram(msg, buttons)
                    info["tp1_hit"] = True
                    info["sl"] = trail_level
                    updated_trades[ticker] = info
                    daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "TP1"})

                elif curr_high >= tp2_price:
                    msg = (
                        f"🏆 *FINAL TARGET 2 (1:2 RRR) ACHIEVED!*\n"
                        f"🏷️ *Quality:* `{trade_grade}` | 🏛️ *Market:* **{market_tag}**\n\n"
                        f"🚀 *Asset:* **{display_name}**\n"
                        f"💵 *LTP:* {currency}{round(curr_price, 2)}\n"
                        f"🎯 *Target 2 Level:* {currency}{tp2_price}\n\n"
                        f"💡 *Action:* **Close remaining position** and lock 1:2 profits!\n\n"
                        f"⚠️ *Disclaimer:* Educational tracking."
                    )
                    send_telegram(msg, buttons)
                    daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "TP2"})
                    continue
                else:
                    updated_trades[ticker] = info

            # PE TRADES
            else:
                if curr_high >= sl_price:
                    msg = (
                        f"🛑 *STOP-LOSS HIT / EXIT ALERT (PE TRADE)*\n"
                        f"🏷️ *Quality:* `{trade_grade}` | 🏛️ *Market:* **{market_tag}**\n\n"
                        f"📉 *Asset:* **{display_name}**\n"
                        f"💵 *Spot Trigger:* {round(curr_price, 2)} (SL: {sl_price})\n"
                        f"💡 *Action:* **Exit PE position** immediately.\n\n"
                        f"⚠️ *Disclaimer:* Algorithmic position tracking."
                    )
                    send_telegram(msg, buttons)
                    daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "SL"})
                    daily_stats["net_loss_today"] += DEFAULT_RISK_PER_TRADE
                    continue

                elif curr_low <= tp1_price and not info.get("tp1_hit", False):
                    msg = (
                        f"🎯 *TARGET 1 ACHIEVED (PE TRADE)!*\n"
                        f"🏷️ *Quality:* `{trade_grade}` | 🏛️ *Market:* **{market_tag}**\n\n"
                        f"🏆 *Asset:* **{display_name}**\n"
                        f"💵 *Spot LTP:* {round(curr_price, 2)}\n"
                        f"🎯 *Target 1 Level:* {tp1_price}\n\n"
                        f"💡 *Action:* **Book 50% PE Profit**, Trail SL to Entry ({entry_price}).\n\n"
                        f"⚠️ *Disclaimer:* Educational tracking."
                    )
                    send_telegram(msg, buttons)
                    info["tp1_hit"] = True
                    info["sl"] = entry_price
                    updated_trades[ticker] = info
                    daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "TP1"})

                elif curr_low <= tp2_price:
                    msg = (
                        f"🏆 *FINAL TARGET 2 ACHIEVED (PE TRADE)!*\n"
                        f"🏷️ *Quality:* `{trade_grade}` | 🏛️ *Market:* **{market_tag}**\n\n"
                        f"🚀 *Asset:* **{display_name}**\n"
                        f"💵 *Spot LTP:* {round(curr_price, 2)}\n"
                        f"🎯 *Target 2 Level:* {tp2_price}\n\n"
                        f"💡 *Action:* **Close full PE position**.\n\n"
                        f"⚠️ *Disclaimer:* Educational tracking."
                    )
                    send_telegram(msg, buttons)
                    daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "TP2"})
                    continue
                else:
                    updated_trades[ticker] = info

        except Exception:
            updated_trades[ticker] = info

    return updated_trades

# -------------------------------------------------------------
# EOD SUMMARY REPORT ENGINE
# -------------------------------------------------------------
def send_eod_summary(sent_cache, daily_stats, today_str, ist_now):
    if (ist_now.hour > 15) or (ist_now.hour == 15 and ist_now.minute >= 30):
        if daily_stats.get("eod_sent_date") == today_str:
            return

        closed = daily_stats.get("closed_trades", [])
        today_closed = [t for t in closed if t.get("date") == today_str]

        tp1_count = sum(1 for t in today_closed if t.get("result") == "TP1")
        tp2_count = sum(1 for t in today_closed if t.get("result") == "TP2")
        sl_count = sum(1 for t in today_closed if t.get("result") == "SL")
        early_count = sum(1 for t in today_closed if t.get("result") == "EARLY_EXIT")
        total_alerts = len(sent_cache)

        eod_msg = (
            f"📋 *END OF DAY (EOD) PERFORMANCE REPORT*\n"
            f"📅 *Date:* `{today_str}` | *Status: NSE SESSION CLOSED*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *Total Alerts Generated:* {total_alerts}\n\n"
            f"✅ *Target 1 Hit (1:1 - 50% Booked):* {tp1_count}\n"
            f"🏆 *Target 2 Hit (1:2 - Full Exit):* {tp2_count}\n"
            f"⚠️ *Early Reversal Exits (Saved SL):* {early_count}\n"
            f"🛑 *Stop-Loss Hit:* {sl_count}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *Risk Capping:* Maintained strict institutional risk discipline.\n\n"
            f"⚠️ *Disclaimer:* Automated study ledger. Not financial advice."
        )

        send_telegram(eod_msg)
        daily_stats["eod_sent_date"] = today_str
        print(f"[{ist_now.strftime('%H:%M IST')}] EOD Report sent.")

# -------------------------------------------------------------
# ULTRA-PRO BATCH SCANNER WITH VISUAL CHARTS & SNIPER ENGINE
# -------------------------------------------------------------
def run_ultra_pro_market_scan(sent_cache, active_trades, daily_stats, ist_now):
    net_loss = daily_stats.get("net_loss_today", 0)
    is_sniper_mode = (net_loss >= DAILY_MAX_LOSS_LIMIT)

    india_vix = get_market_vix()

    indian_market_active = (
        (ist_now.hour == 9 and ist_now.minute >= 15) or 
        (10 <= ist_now.hour < 15) or 
        (ist_now.hour == 15 and ist_now.minute < 15)
    )

    batch_size = 35
    all_tickers = []
    for cat_name, cat_list in MARKET_CATEGORIES.items():
        is_indian = ("INDIAN" in cat_name or "INDEX" in cat_name)
        if is_indian and not indian_market_active:
            continue
        all_tickers.extend(cat_list)

    scan_candidates = [t for t in all_tickers if t not in sent_cache and t not in active_trades]
    if not scan_candidates:
        return

    curr_min = ist_now.minute
    start_window_min = (curr_min // 15) * 15
    start_time_str = ist_now.replace(minute=start_window_min).strftime("%I:%M %p")
    end_time = ist_now.replace(minute=start_window_min) + timedelta(minutes=15)
    end_time_str = end_time.strftime("%I:%M %p IST")
    entry_window_label = f"{start_time_str} - {end_time_str}"

    current_risk_cap = (DEFAULT_RISK_PER_TRADE // 2) if is_sniper_mode else DEFAULT_RISK_PER_TRADE

    for i in range(0, len(scan_candidates), batch_size):
        batch = scan_candidates[i:i + batch_size]
        try:
            data_15m = yf.download(batch, period="5d", interval="15m", group_by='ticker', progress=False)
            
            for ticker in batch:
                try:
                    df_15m = data_15m[ticker] if len(batch) > 1 else data_15m
                    df_15m = df_15m.dropna()
                    if len(df_15m) < 30:
                        continue

                    c_close = float(df_15m['Close'].iloc[-1])
                    c_open = float(df_15m['Open'].iloc[-1])
                    c_vol = float(df_15m['Volume'].iloc[-1])

                    df_15m['VWAP'] = calculate_vwap(df_15m)
                    c_vwap = float(df_15m['VWAP'].iloc[-1])

                    is_index = ticker in INDEX_OPTION_TICKERS
                    prev_window_len = 16 if is_index else 25
                    prev_window = df_15m.iloc[-prev_window_len:-1]
                    res_level = float(prev_window['High'].max())
                    sup_level = float(prev_window['Low'].min())
                    avg_vol = float(prev_window['Volume'].mean()) or 1.0

                    atr_series = ta.volatility.average_true_range(df_15m['High'], df_15m['Low'], df_15m['Close'], window=14)
                    atr = float(atr_series.dropna().iloc[-1]) if not atr_series.dropna().empty else (c_close * 0.005)

                    rsi_series = ta.momentum.rsi(df_15m['Close'], window=14)
                    rsi = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else 50.0

                    ema20_series = ta.trend.ema_indicator(df_15m['Close'], window=20)
                    ema20 = float(ema20_series.dropna().iloc[-1]) if not ema20_series.dropna().empty else c_close

                    ema50_series = ta.trend.ema_indicator(df_15m['Close'], window=50)
                    ema50 = float(ema50_series.dropna().iloc[-1]) if not ema50_series.dropna().empty else c_close

                    is_forex_or_comm = ("=" in ticker or "^" in ticker)
                    rvol = (c_vol / avg_vol) if avg_vol > 0 else 1.0

                    # -------------------------------------------------------------
                    # DYNAMIC SETUP GRADING ENGINE (A+, A, B)
                    # -------------------------------------------------------------
                    if is_forex_or_comm or is_index:
                        trade_grade = "Grade A+ (Institutional)" if (rsi >= 58 or rsi <= 42) else "Grade A"
                    else:
                        if rvol >= 2.5 and (c_close > ema50) and (rsi >= 58):
                            trade_grade = "Grade A+ (High Conviction)"
                        elif rvol >= 1.6 and (rsi >= 53):
                            trade_grade = "Grade A (Institutional)"
                        elif rvol >= 1.3:
                            trade_grade = "Grade B (Momentum Scalp)"
                        else:
                            continue

                    # Sniper Mode Check: When daily loss limit hit, strictly accept Grade A+ only
                    if is_sniper_mode and "Grade A+" not in trade_grade:
                        continue

                    # 1. INDEX OPTIONS (NIFTY / BANK NIFTY ATM)
                    if is_index:
                        bullish_breakout = (c_close > res_level) and (c_close > c_open) and (c_close > ema20) and (c_close > c_vwap) and (rsi >= 52)
                        bearish_breakdown = (c_close < sup_level) and (c_close < c_open) and (c_close < ema20) and (c_close < c_vwap) and (rsi <= 48)

                        if is_sniper_mode:
                            bullish_breakout = bullish_breakout and (c_close > ema50)
                            bearish_breakdown = bearish_breakdown and (c_close < ema50)

                        if not bullish_breakout and not bearish_breakdown:
                            continue

                        index_name = NAME_MAP.get(ticker, ticker)
                        atm_strike, lot_size = get_atm_option_details(ticker, c_close)
                        
                        opt_sl_pts = max(round(atr * 0.4, 1), 18.0 if "NIFTY 50" in index_name else 40.0)
                        opt_tp1_pts = round(opt_sl_pts * 1.0, 1)
                        opt_tp2_pts = round(opt_sl_pts * 2.0, 1)

                        risk_per_lot = opt_sl_pts * lot_size
                        rec_lots = max(1, int(current_risk_cap / risk_per_lot))

                        if bullish_breakout:
                            option_symbol = f"{index_name} {atm_strike} CE"
                            sl_spot = round(c_close - (1.0 * atr), 2)
                            tp1_spot = round(c_close + (1.0 * atr), 2)
                            tp2_spot = round(c_close + (2.0 * atr), 2)
                            action_title = f"🟢 BUY {atm_strike} CALL (CE)"
                            is_pe = False
                        else:
                            option_symbol = f"{index_name} {atm_strike} PE"
                            sl_spot = round(c_close + (1.0 * atr), 2)
                            tp1_spot = round(c_close - (1.0 * atr), 2)
                            tp2_spot = round(c_close - (2.0 * atr), 2)
                            action_title = f"🔴 BUY {atm_strike} PUT (PE)"
                            is_pe = True

                        chart_file = generate_chart_snapshot(df_15m, ticker, option_symbol, round(c_close, 2), sl_spot, tp1_spot, tp2_spot)

                        tv_link = f"https://in.tradingview.com/chart/?symbol={'NIFTY' if 'NIFTY 50' in index_name else 'BANKNIFTY'}"
                        buttons = [[{"text": "📊 Open Index Chart", "url": tv_link}]]

                        sniper_banner = "🎯 *[SNIPER MODE: POST-LOSS HIGH CONVICTION]*\n" if is_sniper_mode else ""

                        msg = (
                            f"{sniper_banner}"
                            f"⚡ *INDEX OPTION MOMENTUM ALERT*\n"
                            f"🏷️ *Setup Quality:* `{trade_grade}`\n"
                            f"🏛️ *Market:* **⚡ INDEX OPTIONS (INTRADAY)**\n\n"
                            f"🎯 *Contract:* **{option_symbol}** ({action_title})\n"
                            f"⏰ *Entry Window:* `{entry_window_label}`\n"
                            f"💵 *Spot LTP:* ₹{round(c_close, 2)} | *VWAP:* ₹{round(c_vwap, 2)} ✅\n\n"
                            f"🛑 *Premium Stop-Loss:* **-{opt_sl_pts} pts** (Spot SL: ₹{sl_spot})\n"
                            f"🎯 *Target 1 (50% Book):* **+{opt_tp1_pts} pts** (1:1 RRR)\n"
                            f"🏆 *Target 2 (Final Exit):* **+{opt_tp2_pts} pts** (1:2 RRR)\n\n"
                            f"⚖️ *Risk : Reward:* **1 : 2.0 (Strict)**\n"
                            f"🧮 *Lot Allocation:* **{rec_lots} Lot ({rec_lots * lot_size} Qty)** (~₹{int(risk_per_lot * rec_lots)} Risk)\n"
                            f"📊 *15m RSI:* {round(rsi, 1)} | *India VIX:* {round(india_vix, 1)}\n\n"
                            f"⚠️ *Disclaimer:* Algorithmic study. Strictly follow stop loss."
                        )

                        send_telegram(msg, buttons, chart_img_path=chart_file)
                        sent_cache.add(ticker)
                        active_trades[ticker] = {
                            "entry": round(c_close, 2),
                            "breakout_level": round(res_level if not is_pe else sup_level, 2),
                            "sl": sl_spot,
                            "tp1": tp1_spot,
                            "tp2": tp2_spot,
                            "currency": "₹",
                            "market": "⚡ INDEX OPTIONS",
                            "display_name": option_symbol,
                            "is_pe": is_pe,
                            "grade": trade_grade,
                            "tp1_hit": False,
                            "date": ist_now.strftime("%Y-%m-%d")
                        }
                        continue

                    # 2. EQUITIES, FOREX, COMMODITIES, CRYPTO
                    if c_close <= res_level or c_close <= c_open or c_close <= c_vwap:
                        continue

                    if is_sniper_mode and c_close <= ema50:
                        continue

                    if rsi < 50 or rsi > 78:
                        continue

                    sl_dist = 1.0 * atr
                    sl = round(c_close - sl_dist, 4 if is_forex_or_comm else 2)
                    tp1 = round(c_close + sl_dist, 4 if is_forex_or_comm else 2)
                    tp2 = round(c_close + (2.0 * sl_dist), 4 if is_forex_or_comm else 2)

                    market_tag = get_market_category(ticker)
                    display_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("-USD", ""))
                    currency = "₹" if ".NS" in ticker else ("$" if ("-USD" in ticker or "=F" in ticker) else "")

                    risk_unit = max(round(c_close - sl, 4 if is_forex_or_comm else 2), 0.0001)
                    rec_qty = max(1, int(current_risk_cap / risk_unit)) if currency == "₹" else max(1, int(25 / risk_unit))

                    chart_file = generate_chart_snapshot(df_15m, ticker, display_name, round(c_close, 2), sl, tp1, tp2)

                    clean_sym = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
                    tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
                    screener_link = f"https://www.screener.in/company/{clean_sym}/" if ".NS" in ticker else f"https://finviz.com/quote.ashx?t={clean_sym}"

                    sniper_banner = "🎯 *[SNIPER MODE: POST-LOSS HIGH CONVICTION]*\n" if is_sniper_mode else ""

                    msg = (
                        f"{sniper_banner}"
                        f"🎯 *NEW BREAKOUT ALERT*\n"
                        f"🏷️ *Setup Quality:* `{trade_grade}`\n"
                        f"🏛️ *Market:* **{market_tag}**\n\n"
                        f"📈 *Asset:* **{display_name}**\n"
                        f"⏰ *Entry Window:* `{entry_window_label}`\n"
                        f"💵 *Reference Entry:* {currency}{round(c_close, 4 if is_forex_or_comm else 2)}\n"
                        f"🌊 *Intraday VWAP:* {currency}{round(c_vwap, 2)} (Passed ✅)\n"
                        f"🛑 *Stop-Loss (SL):* {currency}{sl}\n"
                        f"🎯 *Target 1 (50% Book):* {currency}{tp1} (1:1)\n"
                        f"🏆 *Target 2 (Final Exit):* {currency}{tp2} (1:2)\n\n"
                        f"⚖️ *Risk : Reward:* **1 : 2.0 (Strict)**\n"
                        f"🧮 *Reference Sizing:* ~**{rec_qty} Units** (~₹{current_risk_cap} risk cap)\n"
                        f"📊 *15m RSI:* {round(rsi, 1)} | *RVol:* {round(rvol, 2)}x ✅\n\n"
                        f"⚠️ *Disclaimer:* Educational & algorithmic research only. Not financial advice."
                    )

                    buttons = [
                        [
                            {"text": "📊 Open TradingView", "url": tv_link},
                            {"text": "🔍 Screener Analysis", "url": screener_link}
                        ]
                    ]

                    send_telegram(msg, buttons, chart_img_path=chart_file)
                    sent_cache.add(ticker)
                    active_trades[ticker] = {
                        "entry": round(c_close, 4 if is_forex_or_comm else 2),
                        "breakout_level": round(res_level, 4 if is_forex_or_comm else 2),
                        "sl": sl,
                        "tp1": tp1,
                        "tp2": tp2,
                        "currency": currency,
                        "market": market_tag,
                        "display_name": display_name,
                        "is_pe": False,
                        "grade": trade_grade,
                        "tp1_hit": False,
                        "date": ist_now.strftime("%Y-%m-%d")
                    }
                    print(f"Alert with Chart [{trade_grade}]: {display_name}")
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

    # Global Sleep Guard (11:00 PM - 8:00 AM IST)
    if ist_now.hour >= 23 or ist_now.hour < 8:
        print(f"[{ist_now.strftime('%H:%M IST')}] Night cutoff active (11:00 PM - 8:00 AM). Exiting cleanly.")
        exit(0)

    # Initialize SmartAPI session with Angel One
    init_smart_api()

    cache_data = load_json(CACHE_FILE, {"date": today_str, "tickers": []})
    if cache_data.get("date") != today_str:
        sent_cache = set()
    else:
        sent_cache = set(cache_data.get("tickers", []))

    active_trades = load_json(ACTIVE_TRADES_FILE, {})
    daily_stats = load_json(DAILY_STATS_FILE, {})

    # 1. Monitor active positions (Targets, SL, Early Reversal, Chandelier Trailing)
    active_trades = monitor_active_trades(active_trades, daily_stats, today_str)

    # 2. EOD Performance Report after 03:30 PM IST
    send_eod_summary(sent_cache, daily_stats, today_str, ist_now)

    # 3. Run Ultra-Pro Market Scanner with Live Charts & Grading
    run_ultra_pro_market_scan(sent_cache, active_trades, daily_stats, ist_now)

    # 4. Save state files
    save_json(CACHE_FILE, {"date": today_str, "tickers": list(sent_cache)})
    save_json(ACTIVE_TRADES_FILE, active_trades)
    save_json(DAILY_STATS_FILE, daily_stats)
