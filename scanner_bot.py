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
# CONFIGURATION & CREDENTIALS
# -------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_IDS = [
    "1527960238",         # Personal Chat
    "-1004352653406"       # Private Channel (Quant Move Alerts)
]

CACHE_FILE = "sent_alerts.json"
ACTIVE_TRADES_FILE = "active_trades.json"
DAILY_STATS_FILE = "daily_stats.json"

DEFAULT_RISK_PER_TRADE = 1000  # ₹1,000 risk allocation guide

# -------------------------------------------------------------
# ASSET UNIVERSE
# -------------------------------------------------------------
INDICES = ["^NSEI", "^NSEBANK", "^CNXIT", "^CNXAUTO", "^CNXPHARMA", "^CNXMETAL", "^IXIC"]

GLOBAL_ASSETS = [
    "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "NFLX", "PLTR",
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD",
    "GC=F", "SI=F", "CL=F", "INR=X", "EURUSD=X", "GBPUSD=X"
]

NSE_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS",
    "KOTAKBANK.NS", "LT.NS", "BHARTIARTL.NS", "ITC.NS", "HINDUNILVR.NS", "TATAMOTORS.NS", "MARUTI.NS",
    "M&M.NS", "SUNPHARMA.NS", "CIPLA.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "TITAN.NS",
    "BAJFINANCE.NS", "ADANIENT.NS", "ADANIPORTS.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "COALINDIA.NS",
    "SUZLON.NS", "IREDA.NS", "MAZDOCK.NS", "RVNL.NS", "IRFC.NS", "BSE.NS", "CDSL.NS", "ANGELONE.NS",
    "TATATECH.NS", "HAL.NS", "BEL.NS", "COCHINSHIP.NS", "TRENT.NS", "ZOMATO.NS", "JIOFIN.NS",
    "PERSISTENT.NS", "COFORGE.NS", "DIXON.NS", "POLYCAB.NS", "KEI.NS", "KALYANKJIL.NS", "PRESTIGE.NS",
    "LODHA.NS", "DLF.NS", "SOLARINDS.NS", "TATACOMM.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS", "AUROPHARMA.NS",
    "LUPIN.NS", "GLENMARK.NS", "EXIDEIND.NS", "AMARAJABAT.NS", "ASHOKLEY.NS", "MOTHERSON.NS", "OBEROIRLTY.NS",
    "PHOENIXLTD.NS", "NATIONALUM.NS", "SAIL.NS", "NMDC.NS", "HUDCO.NS", "NBCC.NS", "BHEL.NS"
]

FULL_WATCHLIST = INDICES + GLOBAL_ASSETS + NSE_UNIVERSE

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
    except Exception as e:
        print(f"Error saving {filepath}: {e}")

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
        except Exception as e:
            print(f"Delivery failed for {chat_id}: {e}")

def get_ist_time():
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=5, minutes=30)

def is_market_breadth_favorable():
    try:
        df = yf.download("^NSEI", period="5d", interval="15m", progress=False)
        if df.empty or len(df) < 20:
            return True
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        closes = df['Close'].dropna()
        ema20 = float(ta.trend.ema_indicator(closes, window=20).iloc[-1])
        curr_nifty = float(closes.iloc[-1])
        return curr_nifty >= ema20
    except Exception:
        return True

def run_premarket_briefing_if_due(daily_stats, ist_now):
    today_str = ist_now.strftime("%Y-%m-%d")
    if ist_now.weekday() >= 5:
        return

    if 8 <= ist_now.hour <= 9 and not daily_stats.get("premarket_sent_date") == today_str:
        if ist_now.hour == 8 and ist_now.minute < 30:
            return

        try:
            data = yf.download(["^IXIC", "GC=F", "CL=F"], period="2d", interval="1d", progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                nasdaq_close = float(data['Close']['^IXIC'].dropna().iloc[-1])
                nasdaq_prev = float(data['Close']['^IXIC'].dropna().iloc[-2])
                nasdaq_pct = round(((nasdaq_close - nasdaq_prev) / nasdaq_prev) * 100, 2)

                gold_close = float(data['Close']['GC=F'].dropna().iloc[-1])
                crude_close = float(data['Close']['CL=F'].dropna().iloc[-1])
            else:
                nasdaq_pct = 0.0
                gold_close = 0.0
                crude_close = 0.0

            briefing_msg = (
                f"🌅 *DAILY PRE-MARKET BRIEFING | {today_str}*\n\n"
                f"📊 *Global Sentiments:*\n"
                f"• *Nasdaq (US Tech):* {'🟢' if nasdaq_pct >= 0 else '🔴'} {nasdaq_pct}%\n"
                f"• *Gold Futures:* ${round(gold_close, 1)}\n"
                f"• *Crude Oil:* ${round(crude_close, 2)}\n\n"
                f"🧭 *Risk Rule:* 1-2% portfolio risk limit per trade.\n"
                f"🔔 *Automated scanners are active!*"
            )
            send_telegram(briefing_msg)
            daily_stats["premarket_sent_date"] = today_str
        except Exception as e:
            print(f"Pre-market briefing error: {e}")

def run_eod_summary_if_due(daily_stats, ist_now):
    today_str = ist_now.strftime("%Y-%m-%d")
    if ist_now.weekday() >= 5:
        return

    if ist_now.hour >= 16 and not daily_stats.get("eod_sent_date") == today_str:
        closed_today = [t for t in daily_stats.get("closed_trades", []) if t.get("date") == today_str]
        target_hits = sum(1 for t in closed_today if t.get("result") in ["TP1", "TP2"])
        sl_hits = sum(1 for t in closed_today if t.get("result") in ["SL", "INVALIDATED"])

        summary_msg = (
            f"📋 *END-OF-DAY (EOD) PERFORMANCE SUMMARY*\n"
            f"📅 *Date:* {today_str}\n\n"
            f"🎯 *Target Hits:* {target_hits}\n"
            f"🛑 *SL / Invalidation Exits:* {sl_hits}\n"
            f"📦 *Completed Trades:* {len(closed_today)}\n\n"
            f"💎 Trailing stop-loss monitoring active on running positions."
        )
        send_telegram(summary_msg)
        daily_stats["eod_sent_date"] = today_str

def manage_active_trades(active_trades, daily_stats, today_str):
    if not active_trades:
        return {}

    updated_trades = {}
    tickers = list(active_trades.keys())
    
    try:
        data = yf.download(tickers, period="3d", interval="15m", group_by='ticker', progress=False)
    except Exception as e:
        print(f"Error fetching active trades: {e}")
        return active_trades

    if "closed_trades" not in daily_stats:
        daily_stats["closed_trades"] = []

    for ticker, info in active_trades.items():
        try:
            df = data[ticker] if len(tickers) > 1 else data
            if df.empty or len(df) < 5:
                updated_trades[ticker] = info
                continue

            curr_price = float(df['Close'].dropna().iloc[-1])
            breakout_level = info.get("breakout_level", info["entry"])
            entry_price = info["entry"]
            sl_price = info["sl"]
            tp1_price = info["tp1"]
            tp2_price = info["tp2"]
            trade_type = info["type"]
            currency = info.get("currency", "₹")

            clean_sym = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
            tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
            buttons = [[{"text": "📊 Open TradingView Chart", "url": tv_link}]]

            # SL Breach
            if curr_price <= sl_price:
                msg = (
                    f"🚨 *STOP-LOSS HIT / REVERSAL EXIT*\n\n"
                    f"⚠️ *Asset:* {clean_sym} ({trade_type})\n"
                    f"🛑 *Status:* SL Triggered at {currency}{round(curr_price, 2)}\n"
                    f"💡 *Action:* **Exit immediately** to safeguard capital."
                )
                send_telegram(msg, buttons)
                daily_stats["closed_trades"].append({"date": today_str, "ticker": clean_sym, "result": "SL"})
                continue

            # False Breakout
            elif curr_price < breakout_level and not info.get("tp1_alerted", False):
                c1 = float(df['Close'].dropna().iloc[-1])
                c2 = float(df['Close'].dropna().iloc[-2])
                if c1 < breakout_level and c2 < breakout_level:
                    msg = (
                        f"⚠️ *FALSE BREAKOUT RE-ENTRY*\n\n"
                        f"📉 *Asset:* {clean_sym} ({trade_type})\n"
                        f"🔍 *Note:* Price fell back inside base ({currency}{breakout_level})\n"
                        f"💡 *Action:* Exit near cost."
                    )
                    send_telegram(msg, buttons)
                    daily_stats["closed_trades"].append({"date": today_str, "ticker": clean_sym, "result": "INVALIDATED"})
                    continue

            # Target 1
            elif curr_price >= tp1_price and not info.get("tp1_alerted", False):
                msg = (
                    f"🎯 *TARGET 1 ACHIEVED!*\n\n"
                    f"🏆 *Asset:* {clean_sym} ({trade_type})\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 2)} (Entry: {currency}{entry_price})\n"
                    f"💡 *Action:* **Book 50% Profit**, trail SL to Cost ({currency}{entry_price})."
                )
                send_telegram(msg, buttons)
                info["tp1_alerted"] = True
                info["sl"] = entry_price
                updated_trades[ticker] = info
                daily_stats["closed_trades"].append({"date": today_str, "ticker": clean_sym, "result": "TP1"})

            # Target 2
            elif curr_price >= tp2_price:
                msg = (
                    f"🎉 *FINAL TARGET 2 ACHIEVED!*\n\n"
                    f"🚀 *Asset:* {clean_sym} ({trade_type})\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 2)}\n"
                    f"💡 *Action:* Close full position and lock profit!"
                )
                send_telegram(msg, buttons)
                daily_stats["closed_trades"].append({"date": today_str, "ticker": clean_sym, "result": "TP2"})
                continue
            else:
                updated_trades[ticker] = info
        except Exception:
            updated_trades[ticker] = info

    return updated_trades

def run_batch_market_scan(sent_cache, active_trades):
    breadth_ok = is_market_breadth_favorable()
    batch_size = 40
    all_tickers = [t for t in FULL_WATCHLIST if t not in sent_cache and t not in active_trades]
    
    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i + batch_size]
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
                    c_high = float(df_15m['High'].iloc[-1])
                    c_low = float(df_15m['Low'].iloc[-1])
                    c_vol = float(df_15m['Volume'].iloc[-1])

                    prev_window = df_15m.iloc[-25:-1]
                    res_level = float(prev_window['High'].max())
                    avg_vol = float(prev_window['Volume'].mean()) or 1.0

                    if c_close <= res_level or c_close <= c_open:
                        continue

                    rvol = c_vol / avg_vol
                    if rvol < 1.6 and not ("=" in ticker or "^" in ticker):
                        continue

                    if ".NS" in ticker and not breadth_ok and rvol < 2.5:
                        continue

                    df_d = yf.download(ticker, period="3mo", interval="1d", progress=False)
                    if df_d.empty or len(df_d) < 25:
                        continue
                    if isinstance(df_d.columns, pd.MultiIndex):
                        df_d.columns = [col[0] for col in df_d.columns]

                    d_close = df_d['Close'].dropna()
                    d_high = df_d['High'].dropna()
                    d_low = df_d['Low'].dropna()
                    
                    ema_50 = float(ta.trend.ema_indicator(d_close, window=min(50, len(d_close)-1)).iloc[-1])
                    atr = float(ta.volatility.average_true_range(d_high, d_low, d_close, window=14).iloc[-1])
                    rsi = float(ta.momentum.rsi(d_close, window=14).iloc[-1])
                    recent_high = float(d_high.iloc[-21:-1].max())

                    if c_close < ema_50 or rsi < 48 or rsi > 80:
                        continue

                    is_multiday = c_close > recent_high
                    trade_mode = "📦 SWING / DELIVERY" if is_multiday else "⚡ INTRADAY BREAKOUT"
                    holding = "3 to 10 Days" if is_multiday else "Intraday (Square off ~3:15 PM)"

                    sl = round(c_close - (1.2 * atr if is_multiday else 0.6 * atr), 2)
                    tp1 = round(c_close + (1.8 * atr if is_multiday else 0.9 * atr), 2)
                    tp2 = round(c_close + (3.5 * atr if is_multiday else 1.8 * atr), 2)

                    risk_per_share = max(round(c_close - sl, 2), 0.05)
                    reward_t1 = round(tp1 - c_close, 2)
                    rrr_ratio = round(reward_t1 / risk_per_share, 2)
                    rec_qty = max(1, int(DEFAULT_RISK_PER_TRADE / risk_per_share))

                    grade = "💎 GRADE-A+ (INSTITUTIONAL)" if rvol >= 2.2 else "🔥 GRADE-A MOMENTUM"
                    clean_sym = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
                    currency = "₹" if ".NS" in ticker else "$"

                    tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
                    screener_link = f"https://www.screener.in/company/{clean_sym}/" if ".NS" in ticker else f"https://finviz.com/quote.ashx?t={clean_sym}"

                    msg = (
                        f"🎯 *{grade}*\n\n"
                        f"🏷️ *Mode:* **{trade_mode}**\n"
                        f"⏳ *Horizon:* {holding}\n"
                        f"📈 *Asset:* **{clean_sym}**\n"
                        f"💵 *Entry:* {currency}{round(c_close, 2)}\n"
                        f"🛑 *Stop-Loss (SL):* {currency}{sl}\n"
                        f"🎯 *Target 1 (50% Book):* {currency}{tp1}\n"
                        f"🏆 *Target 2:* {currency}{tp2}\n\n"
                        f"⚖️ *Risk:Reward:* **1 : {rrr_ratio}**\n"
                        f"🧮 *Sizing:* ~**{rec_qty} Qty** (₹1,000 risk cap)\n"
                        f"📊 *15m RVol:* {round(rvol, 1)}x | *RSI:* {round(rsi, 1)}\n\n"
                        f"⚠️ *Disclaimer:* Educational alert only. Maintain strict capital protection."
                    )

                    buttons = [
                        [
                            {"text": "📊 Open TradingView", "url": tv_link},
                            {"text": "🔍 Fundamental Screener", "url": screener_link}
                        ]
                    ]

                    send_telegram(msg, buttons)
                    sent_cache.add(ticker)
                    active_trades[ticker] = {
                        "entry": round(c_close, 2),
                        "breakout_level": round(res_level, 2),
                        "sl": sl,
                        "tp1": tp1,
                        "tp2": tp2,
                        "type": trade_mode,
                        "currency": currency,
                        "tp1_alerted": False
                    }
                    print(f"Triggered alert for {ticker}")

                except Exception:
                    continue

        except Exception as batch_e:
            print(f"Batch error: {batch_e}")

        time.sleep(1)

if __name__ == "__main__":
    ist_now = get_ist_time()
    today_str = ist_now.strftime("%Y-%m-%d")

    cache_data = load_json(CACHE_FILE, {"date": today_str, "tickers": []})
    sent_cache = set(cache_data.get("tickers", [])) if cache_data.get("date") == today_str else set()
    active_trades = load_json(ACTIVE_TRADES_FILE, {})
    daily_stats = load_json(DAILY_STATS_FILE, {})

    run_premarket_briefing_if_due(daily_stats, ist_now)
    active_trades = manage_active_trades(active_trades, daily_stats, today_str)
    run_batch_market_scan(sent_cache, active_trades)
    run_eod_summary_if_due(daily_stats, ist_now)

    save_json(CACHE_FILE, {"date": today_str, "tickers": list(sent_cache)})
    save_json(ACTIVE_TRADES_FILE, active_trades)
    save_json(DAILY_STATS_FILE, daily_stats)
