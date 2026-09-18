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
import requests
import matplotlib
matplotlib.use('Agg')
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
PAPER_TRADES_FILE = "paper_trades.json"
CONFIG_FILE = "system_mode.json"

DEFAULT_RISK_PER_TRADE = 100        # Standard INR risk per trade (₹100 default)
DAILY_MAX_LOSS_LIMIT = 500          # Conservative Sniper loss cap (5 losses)

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
    "CL=F": "CRUDE OIL",
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

def calculate_supertrend(df, period=10, multiplier=3.0):
    atr = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=period)
    hl2 = (df['High'] + df['Low']) / 2
    lowerband = hl2 - (multiplier * atr)
    st_level = lowerband.dropna().iloc[-1] if not lowerband.dropna().empty else float(df['Low'].iloc[-1])
    return float(st_level)

# -------------------------------------------------------------
# VISUAL CHART SNAPSHOT GENERATOR
# -------------------------------------------------------------
def generate_chart_snapshot(df, ticker, display_name, entry, sl, tp1, tp2):
    chart_path = f"/tmp/{ticker.replace('^', '').replace('=', '').replace(':', '')}_chart.png"
    try:
        sub_df = df.iloc[-35:].copy()
        fig, ax = plt.subplots(figsize=(9, 4.8), dpi=120)
        fig.patch.set_facecolor('#131722')
        ax.set_facecolor('#131722')

        for idx, (t, row) in enumerate(sub_df.iterrows()):
            color = '#26a69a' if row['Close'] >= row['Open'] else '#ef5350'
            ax.vlines(x=idx, ymin=row['Low'], ymax=row['High'], color=color, linewidth=1.2)
            body_bottom = min(row['Open'], row['Close'])
            body_top = max(row['Open'], row['Close'])
            body_height = max(body_top - body_bottom, (row['High'] - row['Low']) * 0.05)
            ax.bar(x=idx, height=body_height, bottom=body_bottom, color=color, width=0.6)

        ax.axhline(entry, color='#29b6f6', linestyle='--', linewidth=1.5, label=f'Entry ({entry})')
        ax.axhline(sl, color='#f44336', linestyle='--', linewidth=1.5, label=f'SL ({sl})')
        ax.axhline(tp1, color='#81c784', linestyle=':', linewidth=1.4, label=f'TP1 ({tp1})')
        ax.axhline(tp2, color='#4caf50', linestyle='-', linewidth=1.8, label=f'TP2 ({tp2})')

        ax.set_title(f"{display_name} - 15m Institutional Chart", color='#ffffff', fontsize=12, fontweight='bold', pad=10)
        ax.tick_params(colors='#b2b5be', labelsize=8)
        ax.grid(True, linestyle=':', alpha=0.25, color='#787b86')
        ax.legend(loc='upper left', facecolor='#1e222d', edgecolor='#363c4e', labelcolor='#ffffff', fontsize=8)
        
        plt.tight_layout()
        plt.savefig(chart_path, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)
        return chart_path
    except Exception:
        return None

# -------------------------------------------------------------
# TELEGRAM DISPATCHER
# -------------------------------------------------------------
def send_telegram(text_msg, buttons_data=None, chart_img_path=None):
    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            if chart_img_path and os.path.exists(chart_img_path):
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                payload = {"chat_id": chat_id, "caption": text_msg, "parse_mode": "Markdown"}
                if buttons_data:
                    payload["reply_markup"] = json.dumps({"inline_keyboard": buttons_data})
                with open(chart_img_path, 'rb') as img_f:
                    requests.post(url, data=payload, files={"photo": img_f}, timeout=15)
            else:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {"chat_id": chat_id, "text": text_msg, "parse_mode": "Markdown", "disable_web_page_preview": "true"}
                if buttons_data:
                    payload["reply_markup"] = json.dumps({"inline_keyboard": buttons_data})
                req = urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded"})
                urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    if chart_img_path and os.path.exists(chart_img_path):
        try: os.remove(chart_img_path)
        except Exception: pass

# -------------------------------------------------------------
# ACTIVE TRADES MONITORING & PAPER TRADING TRACKER
# -------------------------------------------------------------
def monitor_active_trades(active_trades, daily_stats, paper_book, today_str):
    if not active_trades:
        return {}

    updated_trades = {}
    tickers = list(active_trades.keys())
    
    try:
        data = yf.download(tickers, period="3d", interval="15m", group_by='ticker', progress=False)
    except Exception:
        return active_trades

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
            sl_price = info["sl"]
            tp1_price = info["tp1"]
            tp2_price = info["tp2"]
            currency = info.get("currency", "")
            display_name = info.get("display_name", ticker)

            if curr_low <= sl_price:
                msg = f"🛑 *STOP-LOSS HIT:* {display_name} hit SL ({currency}{sl_price}). Loss of -₹{DEFAULT_RISK_PER_TRADE} booked."
                send_telegram(msg)
                paper_book["trades"].append({"date": today_str, "asset": display_name, "pnl": -DEFAULT_RISK_PER_TRADE, "status": "SL"})
                paper_book["balance"] -= DEFAULT_RISK_PER_TRADE
                continue

            elif curr_high >= tp1_price and not info.get("tp1_hit", False):
                st_trail = calculate_supertrend(df)
                trail_level = max(entry_price, round(st_trail, 2))
                msg = f"🎯 *TARGET 1 (1:1 RRR) HIT:* {display_name}! Book 50% profit (+₹{int(DEFAULT_RISK_PER_TRADE * 0.5)}). Trail SL to cost ({currency}{trail_level})."
                send_telegram(msg)
                info["tp1_hit"] = True
                info["sl"] = trail_level
                updated_trades[ticker] = info
                paper_book["balance"] += int(DEFAULT_RISK_PER_TRADE * 0.5)

            elif curr_high >= tp2_price:
                msg = f"🏆 *TARGET 2 (1:2 RRR) HIT:* {display_name}! Full profit (+₹{DEFAULT_RISK_PER_TRADE * 2}) locked."
                send_telegram(msg)
                paper_book["trades"].append({"date": today_str, "asset": display_name, "pnl": DEFAULT_RISK_PER_TRADE * 2, "status": "TP2"})
                paper_book["balance"] += DEFAULT_RISK_PER_TRADE * 2
                continue
            else:
                updated_trades[ticker] = info
        except Exception:
            updated_trades[ticker] = info

    return updated_trades

# -------------------------------------------------------------
# DYNAMIC SCANNER ENGINE (BEGINNER VS PRO)
# -------------------------------------------------------------
def run_dynamic_scan(sent_cache, active_trades, daily_stats, paper_book, system_config, ist_now):
    today_str = ist_now.strftime("%Y-%m-%d")
    is_beginner = (system_config.get("mode") == "Beginner (Safe)")
    max_trades = 3 if is_beginner else 999

    trades_today = len([t for t in paper_book.get("trades", []) if t.get("date") == today_str])
    if trades_today >= max_trades:
        print(f"Daily trade limit reached ({trades_today}/{max_trades}). Skipping scan.")
        return

    all_tickers = []
    for cat_name, cat_list in MARKET_CATEGORIES.items():
        if is_beginner and "OPTIONS" in cat_name:
            continue
        all_tickers.extend(cat_list)

    scan_candidates = [t for t in all_tickers if t not in sent_cache and t not in active_trades]
    if not scan_candidates:
        return

    try:
        data = yf.download(scan_candidates[:35], period="5d", interval="15m", group_by='ticker', progress=False)
        for ticker in scan_candidates[:35]:
            try:
                df = data[ticker] if len(scan_candidates[:35]) > 1 else data
                df = df.dropna()
                if len(df) < 25: continue

                c_close = float(df['Close'].iloc[-1])
                c_open = float(df['Open'].iloc[-1])
                c_vol = float(df['Volume'].iloc[-1])
                df['VWAP'] = calculate_vwap(df)
                c_vwap = float(df['VWAP'].iloc[-1])

                res_level = float(df.iloc[-25:-1]['High'].max())
                avg_vol = float(df.iloc[-25:-1]['Volume'].mean()) or 1.0
                atr = float(ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14).dropna().iloc[-1])
                rsi = float(ta.momentum.rsi(df['Close'], window=14).dropna().iloc[-1])
                ema20 = float(ta.trend.ema_indicator(df['Close'], window=20).dropna().iloc[-1])

                rvol = c_vol / avg_vol
                if not (c_close > res_level and c_close > c_open and c_close > ema20 and c_close > c_vwap and rsi >= 52):
                    continue

                sl = round(c_close - (1.0 * atr), 2)
                tp1 = round(c_close + (1.0 * atr), 2)
                tp2 = round(c_close + (2.0 * atr), 2)
                display_name = NAME_MAP.get(ticker, ticker.replace(".NS", ""))
                currency = "₹" if ".NS" in ticker else "$"

                mode_badge = "🛡️ *[BEGINNER SAFE MODE - ₹10,000 LEARNING FUND]*" if is_beginner else "⚡ *[PRO TRADER MODE]*"
                trade_count_str = f"Today's Count: {trades_today + 1}/{max_trades}" if is_beginner else "Unlimited Alert Stream"

                chart_img = generate_chart_snapshot(df, ticker, display_name, c_close, sl, tp1, tp2)

                clean_sym = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
                tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
                terminal_link = "https://vkpdaksh-stock-scanner-app-ffa8vt.streamlit.app"
                
                buttons = [
                    [
                        {"text": "📊 Live Chart", "url": tv_link},
                        {"text": "⚡ Open Web Terminal", "url": terminal_link}
                    ]
                ]

                msg = (
                    f"{mode_badge}\n"
                    f"🎯 *BREAKOUT ALERT:* **{display_name}**\n\n"
                    f"💵 *Reference Entry:* {currency}{c_close:.2f}\n"
                    f"🌊 *Intraday VWAP:* {currency}{c_vwap:.2f} ✅\n"
                    f"🛑 *Stop-Loss (SL):* {currency}{sl:.2f}\n"
                    f"🎯 *Target 1 (1:1 RRR):* {currency}{tp1:.2f} (Book 50%)\n"
                    f"🏆 *Target 2 (1:2 RRR):* {currency}{tp2:.2f} (Runner)\n\n"
                    f"📊 *Volume:* {rvol:.1f}x | *RSI:* {rsi:.1f}\n"
                    f"🚦 *Risk Allocation:* ₹{DEFAULT_RISK_PER_TRADE} (1% Safe Cap)\n"
                    f"📋 *Discipline Rule:* {trade_count_str}\n"
                )

                if is_beginner:
                    msg += (
                        f"\n📚 *Beginner Entry Checklist:*\n"
                        f"• Wait for current 15m candle close.\n"
                        f"• Do not chase if price moved >0.3%.\n"
                        f"• Recorded in Terminal Paper Portfolio.\n"
                    )

                send_telegram(msg, buttons_data=buttons, chart_img_path=chart_img)
                sent_cache.add(ticker)
                active_trades[ticker] = {
                    "entry": c_close, "sl": sl, "tp1": tp1, "tp2": tp2,
                    "currency": currency, "display_name": display_name, "date": today_str
                }
                return
            except Exception:
                continue
    except Exception:
        pass

# -------------------------------------------------------------
# MAIN RUNNER
# -------------------------------------------------------------
if __name__ == "__main__":
    ist_now = get_ist_time()
    today_str = ist_now.strftime("%Y-%m-%d")

    system_config = load_json(CONFIG_FILE, {"mode": "Beginner (Safe)", "execution": "Paper Trading"})
    cache_data = load_json(CACHE_FILE, {"date": today_str, "tickers": []})
    sent_cache = set() if cache_data.get("date") != today_str else set(cache_data.get("tickers", []))

    active_trades = load_json(ACTIVE_TRADES_FILE, {})
    daily_stats = load_json(DAILY_STATS_FILE, {})
    paper_book = load_json(PAPER_TRADES_FILE, {"balance": 10000, "trades": []})

    active_trades = monitor_active_trades(active_trades, daily_stats, paper_book, today_str)
    run_dynamic_scan(sent_cache, active_trades, daily_stats, paper_book, system_config, ist_now)

    save_json(CACHE_FILE, {"date": today_str, "tickers": list(sent_cache)})
    save_json(ACTIVE_TRADES_FILE, active_trades)
    save_json(DAILY_STATS_FILE, daily_stats)
    save_json(PAPER_TRADES_FILE, paper_book)
