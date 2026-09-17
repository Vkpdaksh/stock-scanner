[7:37 am, 17/9/2026] Vikash: import urllib.parse
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
        print(f"Telegram Alert Error: {e}")

def get_nifty_regime():
    """Filter 1: Market Trend Check via Nifty 50 (^NSEI)"""
    try:
        nifty = yf.download("^NSEI", period="1mo", interval="1d", progress=False)
        if nifty.empty:
            return True  # Fallback: agar Nifty data na mile toh trade scan allow karein
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = [col[0] for col in nifty.columns]
        
        close = nifty['Close']
        ema_20 = ta.trend.ema_indicator(close, window=20)
        
        # Nifty apne 20 EMA se upar hona chahiye
        return float(close.iloc[-1]) >= float(ema_20.iloc[-1])
    except Exception as e:
        print(f"Nifty Trend Check Failed: {e}")
        return True

def check_stock(ticker, market_bullish):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df.empty or len(df) < 200:
            return

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        # Advanced Technical Indicators
        rsi = ta.momentum.rsi(close, window=14)
        atr = ta.volatility.average_true_range(high, low, close, window=14)
        ema_50 = ta.trend.ema_indicator(close, window=50)
        ema_200 = ta.trend.ema_indicator(close, window=200)
        vol_sma20 = volume.rolling(window=20).mean()

        ltp = float(close.iloc[-1])
        c_rsi = float(rsi.iloc[-1])
        c_atr = float(atr.iloc[-1])
        c_ema50 = float(ema_50.iloc[-1])
        c_ema200 = float(ema_200.iloc[-1])
        curr_vol = float(volume.iloc[-1]) if not volume.empty else 0
        avg_vol = float(vol_sma20.iloc[-1]) if not vol_sma20.empty else 1

        # Strict Institutional Conditions
        recent_20d_high = float(high.iloc[-21:-1].max())
        is_breakout = ltp > recent_20d_high
        
        # Filter 2: Long-Term & Medium-Term Macro Trend (LTP > EMA 50 > EMA 200)
        is_macro_bullish = (ltp > c_ema50) and (c_ema50 > c_ema200)
        
        # Filter 3: Relative Volume (RVol) >= 1.8x Institutional Surge
        rvol = curr_vol / avg_vol if avg_vol > 0 else 0
        is_volume_confirmed = rvol >= 1.8
        
        # Filter 4: RSI Momentum Filter (RSI 55 - 72: strong momentum without extreme overbought trap)
        is_momentum_healthy = 55 <= c_rsi <= 75

        # All confirmations required
        if is_breakout and is_macro_bullish and is_volume_confirmed and is_momentum_healthy:
            # Dynamic Risk-to-Reward: SL at 1.25x ATR below LTP, TP at 2.5x ATR (1:2 R:R)
            sl = round(ltp - (1.25 * c_atr), 2)
            tp = round(ltp + (2.5 * c_atr), 2)
            sym = ticker.replace(".NS", "")
            
            regime_badge = "🟢 NIFTY ALIGNED" if market_bullish else "⚠️ WEAK MARKET"

            msg = (
                f"💎 INSTITUTIONAL HIGH-CONVICTION BREAKOUT\n\n"
                f"📈 Stock: #{sym}\n"
                f"🌐 Market Context: {regime_badge}\n"
                f"💵 Entry (LTP): ₹{round(ltp, 2)}\n"
                f"🛑 Stop-Loss (SL): ₹{sl}\n"
                f"🏆 Target (TP): ₹{tp} (1:2 R:R)\n"
                f"📊 RVol: {round(rvol, 1)}x Average Volume\n"
                f"⚡ RSI: {round(c_rsi, 1)} | EMA 200: ₹{round(c_ema200, 2)}"
            )
            send_alert(msg)
    except Exception as e:
        print(f"Check failed for {ticker}: {e}")

if _name_ == "_main_":
    is_nifty_bullish = get_nifty_regime()
    for sym in WATCHLIST:
        check_stock(sym, is_nifty_bullish)
[7:52 am, 17/9/2026] Vikash: import urllib.parse
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
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Telegram Alert Error: {e}")

def get_nifty_regime():
    """Market Trend Filter via Nifty 50 (^NSEI)"""
    try:
        nifty = yf.download("^NSEI", period="1mo", interval="1d", progress=False)
        if nifty.empty:
            return True
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = [col[0] for col in nifty.columns]
        
        close = nifty['Close']
        ema_20 = ta.trend.ema_indicator(close, window=20)
        return float(close.iloc[-1]) >= float(ema_20.iloc[-1])
    except Exception as e:
        print(f"Nifty Trend Check Failed: {e}")
        return True

def check_stock(ticker, market_bullish):
    try:
        # Fetching Daily Data for Macro Trend & ATR
        df_daily = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df_daily.empty or len(df_daily) < 50:
            return

        if isinstance(df_daily.columns, pd.MultiIndex):
            df_daily.columns = [col[0] for col in df_daily.columns]

        d_close = df_daily['Close']
        d_high = df_daily['High']
        d_low = df_daily['Low']
        d_vol = df_daily['Volume']

        # Daily Indicators
        ema_50 = ta.trend.ema_indicator(d_close, window=50)
        atr = ta.volatility.average_true_range(d_high, d_low, d_close, window=14)
        vol_sma20 = d_vol.rolling(window=20).mean()

        ltp = float(d_close.iloc[-1])
        c_atr = float(atr.iloc[-1])
        c_ema50 = float(ema_50.iloc[-1]) if not ema_50.empty else ltp
        curr_vol = float(d_vol.iloc[-1]) if not d_vol.empty else 0
        avg_vol = float(vol_sma20.iloc[-1]) if not vol_sma20.empty else 1

        # Macro Trend Check: Stock should be above 50 EMA on Daily
        if ltp < c_ema50:
            return

        # Relative Volume (RVol) check for Institutional Accumulation
        rvol = curr_vol / avg_vol if avg_vol > 0 else 0
        if rvol < 1.6:
            return

        # 20-Day High Breakout Check
        recent_20d_high = float(d_high.iloc[-21:-1].max())
        if ltp <= recent_20d_high:
            return

        # Risk-Reward Targets & Stop Loss Calculation
        sl = round(ltp - (1.2 * c_atr), 2)
        tp1 = round(ltp + (1.5 * c_atr), 2)
        tp2 = round(ltp + (3.0 * c_atr), 2)
        sym = ticker.replace(".NS", "")
        
        # Direct TradingView Quick Link for Manual Order Execution
        tv_link = f"https://in.tradingview.com/chart/?symbol=NSE%3A{sym}"
        regime_badge = "🟢 BULLISH" if market_bullish else "⚠️ CAUTION"

        msg = (
            f"⚡ HIGH-PROBABILITY BREAKOUT ALERT\n\n"
            f"📈 Stock: [{sym}]({tv_link})\n"
            f"🌐 Market Trend: {regime_badge}\n"
            f"💵 LTP: ₹{round(ltp, 2)}\n"
            f"🛑 Stop-Loss: ₹{sl}\n"
            f"🎯 Target 1 (1:1.5): ₹{tp1}\n"
            f"🏆 Target 2 (1:3): ₹{tp2}\n"
            f"📊 Relative Vol (RVol): {round(rvol, 1)}x\n\n"
            f"🔗 [Open Chart in TradingView]({tv_link})"
        )
        send_alert(msg)
    except Exception as e:
        print(f"Check failed for {ticker}: {e}")

if _name_ == "_main_":
    is_nifty_bullish = get_nifty_regime()
    for sym in WATCHLIST:
        check_stock(sym, is_nifty_bullish)
