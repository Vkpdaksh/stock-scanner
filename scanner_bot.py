import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
import pandas as pd
import ta
import yfinance as yf

TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_ID = "1527960238"

CACHE_FILE = "sent_alerts.json"
ACTIVE_TRADES_FILE = "active_trades.json"

WATCHLIST = {
    # Indian Equities
    "RELIANCE.NS": ("^NSEI", "Energy/Oil"),
    "TCS.NS": ("^CNXIT", "IT Sector"),
    "INFY.NS": ("^CNXIT", "IT Sector"),
    "HDFCBANK.NS": ("^NSEBANK", "Banking"),
    "ICICIBANK.NS": ("^NSEBANK", "Banking"),
    "SBIN.NS": ("^NSEBANK", "Banking"),
    "TATAMOTORS.NS": ("^CNXAUTO", "Auto Sector"),
    "TITAN.NS": ("^CNXCONSUM", "Consumer Goods"),
    # US Stocks
    "NVDA": ("^IXIC", "US Tech (NASDAQ)"),
    "TSLA": ("^IXIC", "US Tech (NASDAQ)"),
    # Crypto
    "BTC-USD": ("BTC-USD", "Crypto"),
    "ETH-USD": ("BTC-USD", "Crypto"),
    # Commodities
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
        print(f"Telegram Error: {e}")

def check_sector_trend(sym):
    try:
        df = yf.download(sym, period="1mo", interval="1d", progress=False)
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
    """Monitors open trades for SL Hit, Target Hit, or Adverse Moves"""
    updated_trades = {}
    for ticker, info in active_trades.items():
        try:
            df = yf.download(ticker, period="2d", interval="15m", progress=False)
            if df.empty:
                updated_trades[ticker] = info
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] for col in df.columns]

            curr_price = float(df['Close'].iloc[-1])
            entry_price = info["entry"]
            sl_price = info["sl"]
            tp1_price = info["tp1"]
            tp2_price = info["tp2"]
            trade_type = info["type"]
            currency = info.get("currency", "₹")

            clean_sym = ticker.replace(".NS", "").replace("-USD", "USDT").replace("=F", "")
            tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
            buttons = [[{"text": "📊 View Chart", "url": tv_link}]]

            # Case 1: STOP-LOSS HIT OR ADVERSE REVERSAL
            if curr_price <= sl_price:
                msg = (
                    f"🚨 *STOP-LOSS / EXIT ALERT*\n\n"
                    f"⚠️ *Asset:* {clean_sym} ({trade_type})\n"
                    f"🛑 *Status:* SL Breached / Opposite Direction Move!\n"
                    f"📉 *LTP:* {currency}{round(curr_price, 2)} (SL was {currency}{sl_price})\n"
                    f"💡 *Action:* **EXIT IMMEDIATELY** to preserve capital."
                )
                send_telegram(msg, buttons)
                continue  # Remove from active monitoring

            # Case 2: TARGET 1 HIT
            elif curr_price >= tp1_price and not info.get("tp1_alerted", False):
                msg = (
                    f"🎯 *TARGET 1 REACHED!*\n\n"
                    f"🏆 *Asset:* {clean_sym} ({trade_type})\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 2)} (Entry: {currency}{entry_price})\n"
                    f"💡 *Action:* 50% Profit book karein aur Stop-Loss ko **Cost-to-Cost ({currency}{entry_price})** trail karein!"
                )
                send_telegram(msg, buttons)
                info["tp1_alerted"] = True
                info["sl"] = entry_price  # Trailing SL to Breakeven
                updated_trades[ticker] = info

            # Case 3: TARGET 2 HIT (FULL EXIT)
            elif curr_price >= tp2_price:
                msg = (
                    f"🎉 *FINAL TARGET 2 HIT - FULL PROFIT!*\n\n"
                    f"🚀 *Asset:* {clean_sym} ({trade_type})\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 2)}\n"
                    f"💡 *Action:* Full trade close karein aur profits secure karein!"
                )
                send_telegram(msg, buttons)
                continue  # Completed trade removed

            else:
                updated_trades[ticker] = info
        except Exception as e:
            print(f"Error managing active trade {ticker}: {e}")
            updated_trades[ticker] = info

    return updated_trades

def scan_and_enter(ticker, sector_info, sent_cache, active_trades):
    if ticker in sent_cache or ticker in active_trades:
        return

    try:
        sector_sym, sector_label = sector_info

        # Daily Data (Macro Confluence)
        df_d = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df_d.empty or len(df_d) < 30:
            return
        if isinstance(df_d.columns, pd.MultiIndex):
            df_d.columns = [col[0] for col in df_d.columns]

        d_close = df_d['Close']
        d_high = df_d['High']
        d_low = df_d['Low']
        daily_ema50 = float(ta.trend.ema_indicator(d_close, window=50).iloc[-1])
        daily_atr = float(ta.volatility.average_true_range(d_high, d_low, d_close, window=14).iloc[-1])
        recent_20d_high = float(d_high.iloc[-21:-1].max())

        # 15m Data (Trigger)
        df_15m = yf.download(ticker, period="5d", interval="15m", progress=False)
        if df_15m.empty or len(df_15m) < 30:
            return
        if isinstance(df_15m.columns, pd.MultiIndex):
            df_15m.columns = [col[0] for col in df_15m.columns]

        candle = df_15m.iloc[-2]
        c_close = float(candle['Close'])
        c_open = float(candle['Open'])
        c_high = float(candle['High'])
        c_low = float(candle['Low'])
        c_vol = float(candle['Volume'])

        consolidation_high = float(df_15m.iloc[-22:-2]['High'].max())
        avg_vol = float(df_15m.iloc[-22:-2]['Volume'].mean()) or 1.0

        # Quality Check: Close above 15m resistance, strong body, volume >= 1.5x
        if c_close <= consolidation_high or c_close <= c_open:
            return

        c_range = c_high - c_low
        if c_range > 0 and ((c_close - c_low) / c_range) < 0.70:
            return  # Reject rejection wicks

        rvol = c_vol / avg_vol
        if rvol < 1.4:
            return

        # Classification: INTRADAY vs SWING DELIVERY
        is_daily_breakout = c_close > recent_20d_high and c_close > daily_ema50
        if is_daily_breakout:
            trade_type = "📦 SWING / POSITIONAL (DELIVERY)"
            hold_time = "3 to 10 Days"
            sl = round(c_close - (1.2 * daily_atr), 2)
            tp1 = round(c_close + (1.8 * daily_atr), 2)
            tp2 = round(c_close + (3.5 * daily_atr), 2)
        else:
            trade_type = "⚡ INTRADAY (SAME DAY SQUARE-OFF)"
            hold_time = "Intraday Only (Exit by 3:15 PM)"
            sl = round(c_close - (0.6 * daily_atr), 2)
            tp1 = round(c_close + (0.9 * daily_atr), 2)
            tp2 = round(c_close + (1.8 * daily_atr), 2)

        is_sector_green = check_sector_trend(sector_sym)
        grade = "💎 GRADE-A+ (HIGH CONVICTION)" if is_sector_green and rvol >= 2.0 else "🔥 GRADE-A (CONFIRMED)"

        clean_sym = ticker.replace(".NS", "").replace("-USD", "USDT").replace("=F", "")
        currency = "₹" if ".NS" in ticker else "$"
        tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
        screener_link = f"https://www.screener.in/company/{clean_sym}/" if ".NS" in ticker else f"https://finviz.com/quote.ashx?t={clean_sym}"

        msg = (
            f"🎯 *{grade}*\n\n"
            f"🏷️ *Trade Mode:* **{trade_type}**\n"
            f"⏳ *Holding Period:* {hold_time}\n"
            f"📈 *Asset:* {clean_sym} ({sector_label})\n"
            f"🌐 *Sector Status:* {'🟢 BULLISH' if is_sector_green else '⚠️ NEUTRAL'}\n"
            f"💵 *Entry:* {currency}{round(c_close, 2)}\n"
            f"🛑 *Stop-Loss (SL):* {currency}{sl}\n"
            f"🎯 *Target 1 (Book 50%):* {currency}{tp1}\n"
            f"🏆 *Target 2:* {currency}{tp2}\n"
            f"📊 *Volume Multiplier:* {round(rvol, 1)}x\n\n"
            f"ℹ️ *Exit Rule:* Reverse move / SL breach hote hi alert aayega."
        )

        buttons = [
            [
                {"text": "📊 Open TradingView Chart", "url": tv_link},
                {"text": "🔍 View Details", "url": screener_link}
            ]
        ]

        send_telegram(msg, buttons)
        sent_cache.add(ticker)
        active_trades[ticker] = {
            "entry": round(c_close, 2),
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "type": trade_type,
            "currency": currency,
            "tp1_alerted": False,
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        }
        print(f"Triggered new trade for {ticker}")

    except Exception as e:
        print(f"Error scanning {ticker}: {e}")

if __name__ == "__main__":
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Load Cache & Active Trades
    cache_data = load_json(CACHE_FILE, {"date": today_str, "tickers": []})
    sent_cache = set(cache_data.get("tickers", [])) if cache_data.get("date") == today_str else set()
    active_trades = load_json(ACTIVE_TRADES_FILE, {})

    # 1. Manage & Monitor Running Trades (SL / Target / Exit check)
    active_trades = manage_active_trades(active_trades)

    # 2. Scan For New Confirmed Entries
    for sym, sec_data in WATCHLIST.items():
        scan_and_enter(sym, sec_data, sent_cache, active_trades)

    # Save State
    save_json(CACHE_FILE, {"date": today_str, "tickers": list(sent_cache)})
    save_json(ACTIVE_TRADES_FILE, active_trades)
