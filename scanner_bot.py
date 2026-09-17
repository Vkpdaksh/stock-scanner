import os
import json
import urllib.parse
import urllib.request
from datetime import datetime
import pandas as pd
import ta
import yfinance as yf

# Telegram Bot Credentials
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_ID = "1527960238"

CACHE_FILE = "sent_alerts.json"
ACTIVE_TRADES_FILE = "active_trades.json"

# All 4 Major Markets Included
WATCHLIST = {
    # 1. Indian Equities (NSE)
    "RELIANCE.NS": ("^NSEI", "Indian Energy/Oil"),
    "TCS.NS": ("^CNXIT", "Indian IT"),
    "INFY.NS": ("^CNXIT", "Indian IT"),
    "HDFCBANK.NS": ("^NSEBANK", "Indian Banking"),
    "ICICIBANK.NS": ("^NSEBANK", "Indian Banking"),
    "SBIN.NS": ("^NSEBANK", "Indian Banking"),
    "TATAMOTORS.NS": ("^CNXAUTO", "Indian Auto"),
    "TITAN.NS": ("^CNXCONSUM", "Indian Consumer Goods"),
    
    # 2. US Stocks (Tech Titans)
    "NVDA": ("^IXIC", "US Tech (NASDAQ)"),
    "TSLA": ("^IXIC", "US Tech (NASDAQ)"),
    
    # 3. 24x7 Crypto Assets
    "BTC-USD": ("BTC-USD", "Crypto 24x7"),
    "ETH-USD": ("BTC-USD", "Crypto 24x7"),
    
    # 4. Commodities
    "GC=F": ("GC=F", "Gold/Commodities")
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
    except Exception as e:
        print(f"Error saving {filepath}: {e}")

def send_telegram(text_msg, buttons_data=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
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
        urllib.request.urlopen(req, timeout=12)
    except Exception as e:
        print(f"Telegram Delivery Error: {e}")

def check_sector_health(benchmark_sym):
    try:
        df = yf.download(benchmark_sym, period="1mo", interval="1d", progress=False)
        if df.empty:
            return True
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
        close = df['Close']
        ema_20 = ta.trend.ema_indicator(close, window=20)
        return float(close.iloc[-1]) >= float(ema_20.iloc[-1])
    except Exception:
        return True

def manage_active_trades(active_trades):
    """Monitors running trades: Stop-Loss, Early Invalidation, Targets"""
    updated_trades = {}
    for ticker, info in active_trades.items():
        try:
            df = yf.download(ticker, period="3d", interval="15m", progress=False)
            if df.empty or len(df) < 5:
                updated_trades[ticker] = info
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] for col in df.columns]

            curr_price = float(df['Close'].iloc[-1])
            breakout_level = info.get("breakout_level", info["entry"])
            entry_price = info["entry"]
            sl_price = info["sl"]
            tp1_price = info["tp1"]
            tp2_price = info["tp2"]
            trade_type = info["type"]
            currency = info.get("currency", "₹")

            clean_sym = ticker.replace(".NS", "").replace("-USD", "USDT").replace("=F", "")
            tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
            buttons = [[{"text": "📊 Open TradingView Chart", "url": tv_link}]]

            # 1. HARD STOP-LOSS HIT (Opposite Direction Move)
            if curr_price <= sl_price:
                msg = (
                    f"🚨 *STOP-LOSS HIT / REVERSAL EXIT*\n\n"
                    f"⚠️ *Asset:* {clean_sym} ({trade_type})\n"
                    f"🛑 *Status:* Stop-Loss Breached / Adverse Direction!\n"
                    f"📉 *LTP:* {currency}{round(curr_price, 2)} (SL: {currency}{sl_price})\n"
                    f"💡 *Action:* **EXIT TRADE IMMEDIATELY** to protect capital."
                )
                send_telegram(msg, buttons)
                continue

            # 2. FALSE BREAKOUT EARLY INVALIDATION (Price falls back inside range)
            elif curr_price < breakout_level and not info.get("tp1_alerted", False):
                c1 = float(df['Close'].iloc[-1])
                c2 = float(df['Close'].iloc[-2])
                if c1 < breakout_level and c2 < breakout_level:
                    msg = (
                        f"⚠️ *EARLY WARNING: FALSE BREAKOUT DETECTED*\n\n"
                        f"📉 *Asset:* {clean_sym} ({trade_type})\n"
                        f"🔍 *Reason:* Price fell back inside consolidation ({currency}{breakout_level})\n"
                        f"💵 *LTP:* {currency}{round(curr_price, 2)}\n"
                        f"💡 *Recommendation:* Position close ya cost-to-cost exit karein."
                    )
                    send_telegram(msg, buttons)
                    continue

            # 3. TARGET 1 REACHED (Partial Profit + Trail SL to Cost)
            elif curr_price >= tp1_price and not info.get("tp1_alerted", False):
                msg = (
                    f"🎯 *TARGET 1 ACHIEVED!*\n\n"
                    f"🏆 *Asset:* {clean_sym} ({trade_type})\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 2)} (Entry: {currency}{entry_price})\n"
                    f"💡 *Action:* **50% Profit book karein** aur apna Stop-Loss **Cost-to-Cost ({currency}{entry_price})** trail karein!"
                )
                send_telegram(msg, buttons)
                info["tp1_alerted"] = True
                info["sl"] = entry_price
                updated_trades[ticker] = info

            # 4. TARGET 2 REACHED (Full Exit)
            elif curr_price >= tp2_price:
                msg = (
                    f"🎉 *FINAL TARGET 2 HIT - COMPLETE PROFIT!*\n\n"
                    f"🚀 *Asset:* {clean_sym} ({trade_type})\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 2)}\n"
                    f"💡 *Action:* Full position close karein aur profit lock karein!"
                )
                send_telegram(msg, buttons)
                continue

            else:
                updated_trades[ticker] = info

        except Exception as e:
            print(f"Active trade error for {ticker}: {e}")
            updated_trades[ticker] = info

    return updated_trades

def scan_high_accuracy_setup(ticker, sector_info, sent_cache, active_trades):
    if ticker in sent_cache or ticker in active_trades:
        return

    try:
        sector_sym, sector_label = sector_info

        # --- TIER 1: Daily Higher-Timeframe Filter ---
        df_d = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df_d.empty or len(df_d) < 50:
            return

        if isinstance(df_d.columns, pd.MultiIndex):
            df_d.columns = [col[0] for col in df_d.columns]

        d_close = df_d['Close']
        d_high = df_d['High']
        d_low = df_d['Low']
        
        daily_ema50 = float(ta.trend.ema_indicator(d_close, window=50).iloc[-1])
        daily_atr = float(ta.volatility.average_true_range(d_high, d_low, d_close, window=14).iloc[-1])
        daily_rsi = float(ta.momentum.rsi(d_close, window=14).iloc[-1])
        recent_20d_high = float(d_high.iloc[-21:-1].max())

        # Daily Trend Rule: Must be above Daily 50 EMA and RSI in healthy momentum
        d_ltp = float(d_close.iloc[-1])
        if d_ltp < daily_ema50 or daily_rsi < 50 or daily_rsi > 78:
            return

        # --- TIER 2: 15-Minute Setup with Volatility & VSA ---
        df_15m = yf.download(ticker, period="5d", interval="15m", progress=False)
        if df_15m.empty or len(df_15m) < 35:
            return

        if isinstance(df_15m.columns, pd.MultiIndex):
            df_15m.columns = [col[0] for col in df_15m.columns]

        candle = df_15m.iloc[-2]
        c_close = float(candle['Close'])
        c_open = float(candle['Open'])
        c_high = float(candle['High'])
        c_low = float(candle['Low'])
        c_vol = float(candle['Volume'])

        consolidation_window = df_15m.iloc[-22:-2]
        breakout_resistance = float(consolidation_window['High'].max())
        avg_15m_vol = float(consolidation_window['Volume'].mean()) or 1.0

        # Rule 1: Resistance ke upar candle close honi chahiye
        if c_close <= breakout_resistance or c_close <= c_open:
            return

        # Rule 2: VSA (Upper wick rejection avoid karein - rejection > 28% nahi honi chahiye)
        candle_range = c_high - c_low
        if candle_range > 0:
            closing_ratio = (c_close - c_low) / candle_range
            if closing_ratio < 0.72:
                return

        # Rule 3: Volume Surge (At least 1.6x Institutional Volume)
        rvol = c_vol / avg_15m_vol
        if rvol < 1.6:
            return

        # Rule 4: TTM Volatility Squeeze Expansion Check
        bb_high = ta.volatility.bollinger_hband(consolidation_window['Close'], window=20, window_dev=2).iloc[-1]
        bb_low = ta.volatility.bollinger_lband(consolidation_window['Close'], window=20, window_dev=2).iloc[-1]
        kc_high = ta.volatility.keltner_channel_hband(consolidation_window['High'], consolidation_window['Low'], consolidation_window['Close'], window=20).iloc[-1]
        kc_low = ta.volatility.keltner_channel_lband(consolidation_window['High'], consolidation_window['Low'], consolidation_window['Close'], window=20).iloc[-1]
        was_in_squeeze = (bb_low > kc_low) and (bb_high < kc_high)

        # Rule 5: Sector Trend
        is_sector_green = check_sector_health(sector_sym)

        # Classification: INTRADAY vs SWING DELIVERY
        is_multiday_breakout = c_close > recent_20d_high
        if is_multiday_breakout:
            trade_type = "📦 SWING / POSITIONAL (DELIVERY)"
            holding = "3 to 10 Days"
            sl = round(c_close - (1.2 * daily_atr), 2)
            tp1 = round(c_close + (1.8 * daily_atr), 2)
            tp2 = round(c_close + (3.5 * daily_atr), 2)
        else:
            trade_type = "⚡ INTRADAY (SAME-DAY)"
            holding = "Intraday (Square off by 3:15 PM)"
            sl = round(c_close - (0.6 * daily_atr), 2)
            tp1 = round(c_close + (0.9 * daily_atr), 2)
            tp2 = round(c_close + (1.8 * daily_atr), 2)

        # Conviction Grade
        if is_sector_green and was_in_squeeze and rvol >= 2.2:
            grade = "💎 GRADE-A+ (INSTITUTIONAL HIGH CONVICTION)"
        elif is_sector_green and rvol >= 1.8:
            grade = "🔥 GRADE-A (CONFIRMED MOMENTUM EXPANSION)"
        else:
            grade = "⚡ GRADE-B (VALID BREAKOUT)"

        clean_sym = ticker.replace(".NS", "").replace("-USD", "USDT").replace("=F", "")
        currency = "₹" if ".NS" in ticker else "$"
        tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
        screener_link = f"https://www.screener.in/company/{clean_sym}/" if ".NS" in ticker else f"https://finviz.com/quote.ashx?t={clean_sym}"

        msg = (
            f"🎯 *{grade}*\n\n"
            f"🏷️ *Trade Mode:* **{trade_type}**\n"
            f"⏳ *Holding Horizon:* {holding}\n"
            f"📈 *Asset:* {clean_sym} ({sector_label})\n"
            f"🌐 *Sector Status:* {'🟢 BULLISH' if is_sector_green else '⚠️ NEUTRAL'}\n"
            f"💵 *Entry:* {currency}{round(c_close, 2)}\n"
            f"🛑 *Stop-Loss (SL):* {currency}{sl}\n"
            f"🎯 *Target 1 (Book 50%):* {currency}{tp1}\n"
            f"🏆 *Target 2:* {currency}{tp2}\n"
            f"📊 *15m RVol Surge:* {round(rvol, 1)}x\n"
            f"⚡ *Daily RSI:* {round(daily_rsi, 1)} | *VSA:* Strong Close ✅\n\n"
            f"ℹ️ *Risk Rule:* False breakout ya SL breach par immediate alert aayega."
        )

        buttons = [
            [
                {"text": "📊 Open TradingView Chart", "url": tv_link},
                {"text": "🔍 Fundamental Screener", "url": screener_link}
            ]
        ]

        send_telegram(msg, buttons)
        sent_cache.add(ticker)
        active_trades[ticker] = {
            "entry": round(c_close, 2),
            "breakout_level": round(breakout_resistance, 2),
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "type": trade_type,
            "currency": currency,
            "tp1_alerted": False,
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        }
        print(f"Alert triggered for {ticker}")

    except Exception as e:
        print(f"Error checking {ticker}: {e}")

if __name__ == "__main__":
    if __name__ == "__main__":
    send_telegram("🧪 *Test Alert:* Scanner live hai aur aapke Telegram par successfully message deliver ho raha hai!")
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    cache_data = load_json(CACHE_FILE, {"date": today_str, "tickers": []})
    sent_cache = set(cache_data.get("tickers", [])) if cache_data.get("date") == today_str else set()
    active_trades = load_json(ACTIVE_TRADES_FILE, {})

    # Step 1: Running trades ko check karein (SL hit / False breakout / Target hit)
    active_trades = manage_active_trades(active_trades)

    # Step 2: Naye high-accuracy institutional setups scan karein
    for sym, sec_data in WATCHLIST.items():
        scan_high_accuracy_setup(sym, sec_data, sent_cache, active_trades)

    # Step 3: File state update karein
    save_json(CACHE_FILE, {"date": today_str, "tickers": list(sent_cache)})
    save_json(ACTIVE_TRADES_FILE, active_trades)
