import os
import json
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
import ta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mplfinance as mpf
from telegram import Bot
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------
# CONFIG & SECRETS
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
APP_URL = "https://vkpdaksh-stock-scanner-app-ffa8vt.streamlit.app"
PAPER_TRADES_FILE = "paper_trades.json"

NSE_WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
    "AXISBANK.NS", "KOTAKBANK.NS", "LT.NS", "BHARTIARTL.NS", "ITC.NS", "HINDUNILVR.NS",
    "TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS",
    "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "TITAN.NS", "BAJFINANCE.NS", "ADANIENT.NS"
]

FOREX_COMMODITIES_WATCHLIST = [
    "GC=F", "SI=F", "CL=F", "HG=F", "INR=X", "EURUSD=X", 
    "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X"
]

NAME_MAP = {
    "GC=F": "XAUUSD (Gold)",
    "SI=F": "XAGUSD (Silver)",
    "CL=F": "CRUDE OIL",
    "HG=F": "COPPER",
    "INR=X": "USD/INR",
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "USDJPY=X": "USD/JPY",
    "AUDUSD=X": "AUD/USD",
    "USDCAD=X": "USD/CAD",
    "USDCHF=X": "USD/CHF",
    "NZDUSD=X": "NZD/USD"
}

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

def calculate_vwap(df):
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    vol = df['Volume'].replace(0, 1)
    return (typical_price * vol).cumsum() / vol.cumsum()

def generate_candlestick_chart(df, ticker, entry, sl, tp1, tp2):
    clean_sym = ticker.replace('.NS', '').replace('=F', '').replace('=X', '')
    chart_filename = f"/tmp/{clean_sym}_chart.png"
    sub_df = df.iloc[-35:].copy()
    sub_df.index = pd.to_datetime(sub_df.index)

    lines = [
        mpf.make_addplot([entry]*len(sub_df), color='#00e676', width=1.0, linestyle='-'),
        mpf.make_addplot([sl]*len(sub_df), color='#ff1744', width=1.0, linestyle='--'),
        mpf.make_addplot([tp1]*len(sub_df), color='#00b0ff', width=1.0, linestyle=':'),
        mpf.make_addplot([tp2]*len(sub_df), color='#76ff03', width=1.0, linestyle=':')
    ]

    mc = mpf.make_marketcolors(up='#00e676', down='#ff1744', edge='inherit', wick='inherit', volume='in')
    s = mpf.make_mpf_style(base_mpf_style='nightclouds', marketcolors=mc, gridcolor='#263238', facecolor='#10141e')

    fig, axlist = mpf.plot(
        sub_df,
        type='candle',
        addplot=lines,
        style=s,
        returnfig=True,
        figsize=(7, 3.8),
        tight_layout=True
    )
    display_title = NAME_MAP.get(ticker, clean_sym)
    axlist[0].set_title(f"{display_title} - 15m Institutional Chart", color='#eceff1', fontsize=10)
    fig.savefig(chart_filename, bbox_inches='tight', facecolor='#10141e', dpi=120)
    plt.close(fig)
    return chart_filename

async def scan_and_alert():
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("Telegram secrets missing.")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    paper_data = load_json(PAPER_TRADES_FILE, {"balance": 10000, "trades": []})
    ist_now = get_ist_now()

    # Time-Based Switching: Scan Forex/Commodities from 3:30 PM to next morning
    if (ist_now.hour >= 16) or (ist_now.hour == 15 and ist_now.minute >= 30) or (ist_now.hour < 9):
        current_pool = FOREX_COMMODITIES_WATCHLIST
        pool_type = "FOREX & COMMODITIES"
    else:
        current_pool = NSE_WATCHLIST
        pool_type = "INDIAN EQUITIES"

    try:
        raw_data = yf.download(current_pool, period="5d", interval="15m", group_by='ticker', progress=False)
    except Exception as e:
        print(f"Data fetch error: {e}")
        return

    today_str = ist_now.strftime("%Y-%m-%d")
    today_trades = [t for t in paper_data.get("trades", []) if t.get("date", "").startswith(today_str)]
    alert_count = len(today_trades)

    for ticker in current_pool:
        try:
            df = raw_data[ticker].dropna() if len(current_pool) > 1 else raw_data.dropna()
            if len(df) < 25:
                continue

            c_close = float(df['Close'].iloc[-1])
            c_open = float(df['Open'].iloc[-1])
            c_vol = float(df['Volume'].iloc[-1])

            df['VWAP'] = calculate_vwap(df)
            c_vwap = float(df['VWAP'].iloc[-1])

            prev_window = df.iloc[-25:-1]
            res_level = float(prev_window['High'].max())
            sup_level = float(prev_window['Low'].min())
            avg_vol = float(prev_window['Volume'].mean()) or 1.0

            is_special = ("=" in ticker or "-USD" in ticker)
            rvol = round(c_vol / avg_vol, 2) if avg_vol > 0 else 1.0
            rsi = float(ta.momentum.rsi(df['Close'], window=14).dropna().iloc[-1])
            ema20 = float(ta.trend.ema_indicator(df['Close'], window=20).dropna().iloc[-1])
            ema50 = float(ta.trend.ema_indicator(df['Close'], window=50).dropna().iloc[-1])

            atr_s = ta.volatility.average_true_range(df['High'], df['Low'], df['Close'], window=14)
            atr = float(atr_s.dropna().iloc[-1]) if not atr_s.dropna().empty else (c_close * 0.005)

            is_breakout = (c_close > res_level) and (c_close > c_open) and (c_close > ema20)
            is_breakdown = (c_close < sup_level) and (c_close < c_open) and (c_close < ema20)

            if not (is_breakout or is_breakdown):
                continue

            # Grading logic (Forex volume is liquid, uses momentum criteria)
            if is_breakout:
                direction = "BUY"
                if (rvol >= 2.0 or is_special) and (c_close > ema50) and (rsi >= 58):
                    grade_badge = "🎯 [GRADE A+ SNIPER BREAKOUT]"
                    grade_name = "Grade A+ (Institutional Sniper)"
                elif (rvol >= 1.3 or is_special) and (rsi >= 52):
                    grade_badge = "🏛️ [GRADE A INSTITUTIONAL BREAKOUT]"
                    grade_name = "Grade A (Institutional Volume)"
                else:
                    grade_badge = "🛡️ [GRADE B / SAFE SCALP]"
                    grade_name = "Grade B (Safe Setup)"
            else:
                direction = "SELL"
                if (rvol >= 2.0 or is_special) and (c_close < ema50) and (rsi <= 42):
                    grade_badge = "🎯 [GRADE A+ SNIPER BREAKDOWN]"
                    grade_name = "Grade A+ (Institutional Sniper)"
                elif (rvol >= 1.3 or is_special) and (rsi <= 48):
                    grade_badge = "🏛️ [GRADE A INSTITUTIONAL BREAKDOWN]"
                    grade_name = "Grade A (Institutional Volume)"
                else:
                    grade_badge = "🛡️ [GRADE B / SAFE SCALP]"
                    grade_name = "Grade B (Safe Setup)"

            sym_name = NAME_MAP.get(ticker, ticker.replace(".NS", ""))
            already_open = any(t.get("asset") == sym_name and t.get("status") == "OPEN" for t in paper_data.get("trades", []))
            if already_open:
                continue

            sl_dist = 1.0 * atr
            decimals = 4 if ("USD" in ticker or "=X" in ticker) else 2
            if direction == "BUY":
                sl = round(c_close - sl_dist, decimals)
                tp1 = round(c_close + (1.0 * sl_dist), decimals)
                tp2 = round(c_close + (2.0 * sl_dist), decimals)
            else:
                sl = round(c_close + sl_dist, decimals)
                tp1 = round(c_close - (1.0 * sl_dist), decimals)
                tp2 = round(c_close - (2.0 * sl_dist), decimals)

            chart_img = generate_candlestick_chart(df, ticker, c_close, sl, tp1, tp2)
            alert_count += 1
            vol_disp = "Liquid Feed" if is_special else f"{rvol}x"

            caption_text = (
                f"{grade_badge}\n"
                f"🌍 MARKET: {pool_type}\n"
                f"🚀 {direction} SIGNAL: {sym_name}\n\n"
                f"📊 Setup Quality: {grade_name}\n"
                f"💵 Reference Entry: {c_close:.{decimals}f}\n"
                f"🌊 Intraday VWAP: {c_vwap:.{decimals}f} ✅\n"
                f"🛑 Stop-Loss (SL): {sl:.{decimals}f}\n"
                f"🎯 Target 1 (1:1 RRR): {tp1:.{decimals}f} (50% Exit)\n"
                f"🏆 Target 2 (1:2 RRR): {tp2:.{decimals}f} (Runner)\n\n"
                f"📊 Volume: {vol_disp} | RSI: {rsi:.1f}\n"
                f"🚦 Risk Allocation: ₹100 (Safe Budget)\n"
                f"📋 Daily Trade Count: {alert_count}/3\n\n"
                f"🔗 Live App: {APP_URL}"
            )

            with open(chart_img, 'rb') as photo:
                await bot.send_photo(
                    chat_id=TELEGRAM_CHAT_ID,
                    photo=photo,
                    caption=caption_text
                )

            risk_unit = max(abs(c_close - sl), 0.0001)
            calc_qty = max(1, int(100 / risk_unit))

            paper_data["trades"].append({
                "date": ist_now.strftime("%Y-%m-%d %H:%M"),
                "asset": sym_name,
                "type": direction,
                "entry": c_close,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "qty": calc_qty,
                "status": "OPEN",
                "grade": grade_name
            })
            save_json(PAPER_TRADES_FILE, paper_data)
            print(f"Alert sent for {sym_name} ({grade_name})")
            break

        except Exception as err:
            print(f"Error scanning {ticker}: {err}")
            continue

if __name__ == "__main__":
    asyncio.run(scan_and_alert())
