import urllib.parse
import urllib.request
import pandas as pd
import ta
import yfinance as yf

# Telegram Credentials
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_ID = "1527960238"

ASSETS = {
    "INDIAN_STOCKS": [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS",
        "INFY.NS", "TATAMOTORS.NS", "SBIN.NS", "TITAN.NS"
    ],
    "US_STOCKS": [
        "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META"
    ],
    "CRYPTO": [
        "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"
    ],
    "FOREX_COMMODITIES": [
        "GC=F", "CL=F", "EURUSD=X", "GBPUSD=X", "USDINR=X"
    ]
}

def send_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"Telegram Delivery Error: {e}")

def get_market_trend(symbol):
    try:
        data = yf.download(symbol, period="1mo", interval="1d", progress=False)
        if data.empty:
            return True
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [col[0] for col in data.columns]
        close = data['Close']
        ema_20 = ta.trend.ema_indicator(close, window=20)
        return float(close.iloc[-1]) >= float(ema_20.iloc[-1])
    except Exception:
        return True

def get_tv_link(ticker, category):
    if category == "INDIAN_STOCKS":
        sym = ticker.replace(".NS", "")
        return f"https://in.tradingview.com/chart/?symbol=NSE%3A{sym}", sym, "₹"
    elif category == "CRYPTO":
        sym = ticker.replace("-USD", "USDT")
        return f"https://in.tradingview.com/chart/?symbol=BINANCE%3A{sym}", ticker, "$"
    elif category == "US_STOCKS":
        return f"https://in.tradingview.com/chart/?symbol=NASDAQ%3A{ticker}", ticker, "$"
    else:
        clean_sym = ticker.replace("=X", "").replace("=F", "")
        return f"https://in.tradingview.com/chart/?symbol={clean_sym}", ticker, ""

def scan_symbol(ticker, category, market_bullish):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df.empty or len(df) < 30:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        ema_50 = ta.trend.ema_indicator(close, window=50)
        atr = ta.volatility.average_true_range(high, low, close, window=14)
        vol_sma20 = volume.rolling(window=20).mean()
        rsi = ta.momentum.rsi(close, window=14)

        ltp = float(close.iloc[-1])
        c_atr = float(atr.iloc[-1]) if not atr.empty else (ltp * 0.02)
        c_ema50 = float(ema_50.iloc[-1]) if not ema_50.empty else ltp
        curr_vol = float(volume.iloc[-1]) if not volume.empty else 0
        avg_vol = float(vol_sma20.iloc[-1]) if not vol_sma20.empty else 1
        c_rsi = float(rsi.iloc[-1]) if not rsi.empty else 50

        # Breakout condition: last 20 candle high breakout
        recent_high = float(high.iloc[-21:-1].max()) if len(high) >= 22 else float(high.max())
        is_breakout = ltp > recent_high and ltp >= c_ema50

        rvol = curr_vol / avg_vol if avg_vol > 0 else 1.0

        if not is_breakout:
            return None

        # Grade logic
        if market_bullish and rvol >= 1.6 and (50 <= c_rsi <= 75):
            grade = "💎 GRADE-A+ (INSTITUTIONAL HIGH-CONVICTION)"
        elif rvol >= 1.3:
            grade = "🔥 GRADE-A (STRONG MOMENTUM BREAKOUT)"
        else:
            grade = "⚡ GRADE-B (BREAKOUT)"

        sl = round(ltp - (1.2 * c_atr), 2)
        tp1 = round(ltp + (1.5 * c_atr), 2)
        tp2 = round(ltp + (3.0 * c_atr), 2)

        tv_link, sym_clean, currency = get_tv_link(ticker, category)
        regime_badge = "🟢 BULLISH" if market_bullish else "⚠️ CAUTION"

        category_labels = {
            "INDIAN_STOCKS": "🇮🇳 Indian Equity",
            "US_STOCKS": "🇺🇸 US Stock",
            "CRYPTO": "🪙 Crypto",
            "FOREX_COMMODITIES": "🌐 Forex/Commodity"
        }

        msg = (
            f"🎯 *{grade}*\n\n"
            f"🏷️ *Market:* {category_labels.get(category, category)}\n"
            f"📈 *Asset:* [{sym_clean}]({tv_link})\n"
            f"🌐 *Macro Context:* {regime_badge}\n"
            f"💵 *LTP:* {currency}{round(ltp, 2)}\n"
            f"🛑 *Stop-Loss:* {currency}{sl}\n"
            f"🎯 *Target 1 (1:1.5):* {currency}{tp1}\n"
            f"🏆 *Target 2 (1:3):* {currency}{tp2}\n"
            f"📊 *Volume Surge:* {round(rvol, 1)}x\n"
            f"⚡ *RSI:* {round(c_rsi, 1)}\n\n"
            f"🔗 [Open Chart in TradingView]({tv_link})"
        )
        return msg
    except Exception as e:
        print(f"Error scanning {ticker}: {e}")
        return None

if __name__ == "__main__":
    nifty_bullish = get_market_trend("^NSEI")
    spx_bullish = get_market_trend("^GSPC")
    btc_bullish = get_market_trend("BTC-USD")

    total_scanned = 0
    alerts_fired = 0

    # 1. Indian Stocks
    for sym in ASSETS["INDIAN_STOCKS"]:
        total_scanned += 1
        msg = scan_symbol(sym, "INDIAN_STOCKS", nifty_bullish)
        if msg:
            send_alert(msg)
            alerts_fired += 1

    # 2. US Stocks
    for sym in ASSETS["US_STOCKS"]:
        total_scanned += 1
        msg = scan_symbol(sym, "US_STOCKS", spx_bullish)
        if msg:
            send_alert(msg)
            alerts_fired += 1

    # 3. Crypto Assets
    for sym in ASSETS["CRYPTO"]:
        total_scanned += 1
        msg = scan_symbol(sym, "CRYPTO", btc_bullish)
        if msg:
            send_alert(msg)
            alerts_fired += 1

    # 4. Forex & Commodities
    for sym in ASSETS["FOREX_COMMODITIES"]:
        total_scanned += 1
        msg = scan_symbol(sym, "FOREX_COMMODITIES", True)
        if msg:
            send_alert(msg)
            alerts_fired += 1

    print(f"Scan finished. Total Scanned: {total_scanned}, Alerts sent: {alerts_fired}")
