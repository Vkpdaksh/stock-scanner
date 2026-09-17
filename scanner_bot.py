import urllib.parse
import urllib.request
import pandas as pd
import ta
import yfinance as yf

# Telegram Credentials
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_ID = "1527960238"

WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "BHARTIARTL.NS", "ITC.NS", "LT.NS", "TATAMOTORS.NS", "SBIN.NS",
    "ADANIENT.NS", "SUNPHARMA.NS", "BAJFINANCE.NS", "TITAN.NS", "TATASTEEL.NS"
]

def send_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

def check_stock(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df.empty or len(df) < 50:
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        rsi = ta.momentum.rsi(close, window=14)
        atr = ta.volatility.average_true_range(high, low, close, window=14)
        vol_sma = volume.rolling(window=20).mean()
        ema_50 = ta.trend.ema_indicator(close, window=50)

        ltp = float(close.iloc[-1])
        recent_high = float(high.iloc[-21:-1].max())
        curr_vol = float(volume.iloc[-1]) if not volume.empty else 0
        avg_vol = float(vol_sma.iloc[-1]) if not vol_sma.empty else 1
        curr_ema = float(ema_50.iloc[-1])

        is_breakout = ltp > recent_high
        is_volume_spike = curr_vol > (1.5 * avg_vol)
        is_trend_up = ltp > curr_ema

        if is_breakout and is_trend_up:
            sig = "🚀 STRONG BREAKOUT" if is_volume_spike else "🔥 BREAKOUT"
            c_atr = float(atr.iloc[-1])
            sl = round(ltp - c_atr, 2)
            tp = round(ltp + (2 * c_atr), 2)
            sym = ticker.replace(".NS", "")

            msg = (
                f"🚨 Cloud Background Alert!\n\n"
                f"📈 Stock: {sym}\n"
                f"🎯 Signal: {sig}\n"
                f"💵 LTP: ₹{round(ltp, 2)}\n"
                f"🛑 SL: ₹{sl}\n"
                f"🏆 TP: ₹{tp}\n"
                f"📊 RSI: {round(float(rsi.iloc[-1]), 1)}"
            )
            send_alert(msg)
    except Exception as e:
        print(f"Check failed for {ticker}: {e}")

if __name__ == "__main__":
    for sym in WATCHLIST:
        check_stock(sym
