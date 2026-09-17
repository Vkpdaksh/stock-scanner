import os
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
import pandas as pd
import ta
import yfinance as yf
import requests

# -------------------------------------------------------------
# CREDENTIALS & STORAGE
# -------------------------------------------------------------
TELEGRAM_BOT_TOKEN = "8732059380:AAGF7qoak6yPiI5ToYGPLSVQQM4GChhKriI"
TELEGRAM_CHAT_IDS = [
    "1527960238",         # Personal Chat
    "-1004352653406"       # Private Channel (Quant Move Alerts)
]

CACHE_FILE = "sent_alerts.json"
ACTIVE_TRADES_FILE = "active_trades.json"
DAILY_STATS_FILE = "daily_stats.json"

DEFAULT_RISK_PER_TRADE = 1000  # ₹1,000 reference risk

# -------------------------------------------------------------
# FIXED GLOBAL ASSETS (GOLD, SILVER, FOREX, CRYPTO)
# -------------------------------------------------------------
COMMODITIES = [
    "XAUUSD=X",  # Gold Spot
    "XAGUSD=X",  # Silver Spot
    "GC=F",      # Gold Futures
    "SI=F",      # Silver Futures
    "CL=F",      # Crude Oil
    "HG=F"       # Copper
]

FOREX_PAIRS = [
    "INR=X",       # USD / INR
    "EURUSD=X",    # EUR / USD
    "GBPUSD=X",    # GBP / USD
    "USDJPY=X",    # USD / JPY
    "AUDUSD=X",    # AUD / USD
    "USDCAD=X",    # USD / CAD
    "USDCHF=X",    # USD / CHF
    "NZDUSD=X"     # NZD / USD
]

CRYPTO_ASSETS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "LINK-USD", "SUI-USD"
]

INDICES = ["^NSEI", "^NSEBANK", "^IXIC"]

NAME_MAP = {
    "XAUUSD=X": "GOLD Spot (XAU/USD)",
    "XAGUSD=X": "SILVER Spot (XAG/USD)",
    "GC=F": "GOLD Futures (Comex)",
    "SI=F": "SILVER Futures (Comex)",
    "CL=F": "CRUDE OIL (WTI)",
    "HG=F": "COPPER FUTURES",
    "INR=X": "USD/INR (Dollar / Rupee)",
    "EURUSD=X": "EUR/USD (Euro / Dollar)",
    "GBPUSD=X": "GBP/USD (Pound / Dollar)",
    "USDJPY=X": "USD/JPY (Dollar / Yen)",
    "AUDUSD=X": "AUD/USD (Aussie / Dollar)",
    "USDCAD=X": "USD/CAD (Dollar / Loonie)",
    "USDCHF=X": "USD/CHF (Dollar / Swiss Franc)",
    "NZDUSD=X": "NZD/USD (Kiwi / Dollar)",
    "BTC-USD": "BITCOIN (24x7)",
    "ETH-USD": "ETHEREUM (24x7)",
    "SOL-USD": "SOLANA (24x7)",
    "^NSEI": "NIFTY 50 INDEX",
    "^NSEBANK": "BANK NIFTY INDEX"
}

# -------------------------------------------------------------
# DYNAMIC LOAD: NIFTY 500 + NASDAQ 100
# -------------------------------------------------------------
def get_dynamic_universe():
    universe = set(COMMODITIES + FOREX_PAIRS + CRYPTO_ASSETS + INDICES)
    
    # 1. Fetch Complete NIFTY 500 List
    try:
        url_nifty500 = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url_nifty500, headers=headers, timeout=10)
        if res.status_code == 200:
            lines = res.text.splitlines()
            df_nse = pd.read_csv(pd.io.common.StringIO("\n".join(lines)))
            nse_symbols = [f"{sym.strip()}.NS" for sym in df_nse['Symbol'].dropna().tolist()]
            universe.update(nse_symbols)
    except Exception:
        pass

    # 2. Fetch Complete NASDAQ 100 List
    try:
        url_nasdaq = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = pd.read_html(url_nasdaq)
        for tbl in tables:
            if "Ticker" in tbl.columns:
                universe.update(tbl['Ticker'].dropna().tolist())
                break
            elif "Symbol" in tbl.columns:
                universe.update(tbl['Symbol'].dropna().tolist())
                break
    except Exception:
        pass

    return list(universe)

# -------------------------------------------------------------
# HELPER FUNCTIONS
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

def is_market_breadth_favorable():
    try:
        df = yf.download("^NSEI", period="5d", interval="15m", progress=False)
        if df.empty or len(df) < 20:
            return True
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        closes = df['Close'].dropna()
        ema20 = float(ta.trend.ema_indicator(closes, window=20).iloc[-1])
        return float(closes.iloc[-1]) >= ema20
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
            data = yf.download(["^IXIC", "GC=F", "CL=F", "INR=X"], period="2d", interval="1d", progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                nasdaq_close = float(data['Close']['^IXIC'].dropna().iloc[-1])
                nasdaq_prev = float(data['Close']['^IXIC'].dropna().iloc[-2])
                nasdaq_pct = round(((nasdaq_close - nasdaq_prev) / nasdaq_prev) * 100, 2)
                gold_close = float(data['Close']['GC=F'].dropna().iloc[-1])
                crude_close = float(data['Close']['CL=F'].dropna().iloc[-1])
                usd_inr = float(data['Close']['INR=X'].dropna().iloc[-1])
            else:
                nasdaq_pct, gold_close, crude_close, usd_inr = 0.0, 0.0, 0.0, 0.0

            briefing_msg = (
                f"🌅 *DAILY PRE-MARKET BRIEFING | {today_str}*\n\n"
                f"📊 *Global Sentiments:*\n"
                f"• *Nasdaq (US Tech):* {'🟢' if nasdaq_pct >= 0 else '🔴'} {nasdaq_pct}%\n"
                f"• *Gold:* ${round(gold_close, 1)} | *Crude:* ${round(crude_close, 2)}\n"
                f"• *USD/INR:* ₹{round(usd_inr, 2)}\n\n"
                f"🧭 *Universe Active:* Nifty 500 + Nasdaq 100 + Crypto + Forex + Gold/Silver.\n"
                f"🔔 *Automated scanners are live!*"
            )
            send_telegram(briefing_msg)
            daily_stats["premarket_sent_date"] = today_str
        except Exception:
            pass

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

# -------------------------------------------------------------
# ACTIVE POSITIONS MONITORING
# -------------------------------------------------------------
def manage_active_trades(active_trades, daily_stats, today_str):
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
            currency = info.get("currency", "")
            display_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("-USD", ""))

            clean_sym = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
            tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
            buttons = [[{"text": "📊 Open TradingView Chart", "url": tv_link}]]

            if curr_price <= sl_price:
                msg = (
                    f"🚨 *STOP-LOSS HIT / REVERSAL EXIT*\n\n"
                    f"⚠️ *Asset:* {display_name} ({trade_type})\n"
                    f"🛑 *Status:* SL Triggered at {currency}{round(curr_price, 4)}\n"
                    f"💡 *Action:* **Exit immediately** to protect capital."
                )
                send_telegram(msg, buttons)
                daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "SL"})
                continue

            elif curr_price < breakout_level and not info.get("tp1_alerted", False):
                c1 = float(df['Close'].dropna().iloc[-1])
                c2 = float(df['Close'].dropna().iloc[-2])
                if c1 < breakout_level and c2 < breakout_level:
                    msg = (
                        f"⚠️ *FALSE BREAKOUT RE-ENTRY*\n\n"
                        f"📉 *Asset:* {display_name} ({trade_type})\n"
                        f"🔍 *Note:* Price fell inside base ({currency}{breakout_level})\n"
                        f"💡 *Action:* Exit near cost."
                    )
                    send_telegram(msg, buttons)
                    daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "INVALIDATED"})
                    continue

            elif curr_price >= tp1_price and not info.get("tp1_alerted", False):
                msg = (
                    f"🎯 *TARGET 1 ACHIEVED!*\n\n"
                    f"🏆 *Asset:* {display_name} ({trade_type})\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 4)} (Entry: {currency}{entry_price})\n"
                    f"💡 *Action:* **Book 50% Profit**, trail SL to Cost ({currency}{entry_price})."
                )
                send_telegram(msg, buttons)
                info["tp1_alerted"] = True
                info["sl"] = entry_price
                updated_trades[ticker] = info
                daily_stats["closed_trades"].append({"date": today_str, "ticker": display_name, "result": "TP1"})

            elif curr_price >= tp2_price:
                msg = (
                    f"🎉 *FINAL TARGET 2 ACHIEVED!*\n\n"
                    f"🚀 *Asset:* {display_name} ({trade_type})\n"
                    f"💵 *LTP:* {currency}{round(curr_price, 4)}\n"
                    f"💡 *Action:* Close full position and lock peak profit!"
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
# BATCH SCANNER (40 PER GROUP)
# -------------------------------------------------------------
def run_batch_market_scan(full_universe, sent_cache, active_trades):
    breadth_ok = is_market_breadth_favorable()
    batch_size = 40
    all_tickers = [t for t in full_universe if t not in sent_cache and t not in active_trades]

    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i + batch_size]
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
                    
                    if not is_forex_or_comm and rvol < 1.6:
                        continue

                    if ".NS" in ticker and not breadth_ok and rvol < 2.5:
                        continue

                    df_d = yf.download(ticker, period="3mo", interval="1d", progress=False)
                    if df_d.empty or len(df_d) < 20:
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

                    if c_close < ema_50 or rsi < 46 or rsi > 82:
                        continue

                    is_multiday = c_close > recent_high
                    trade_mode = "📦 SWING BREAKOUT" if is_multiday else "⚡ INTRADAY BREAKOUT"
                    holding = "3 to 10 Days" if is_multiday else "Intraday"

                    sl = round(c_close - (1.2 * atr if is_multiday else 0.6 * atr), 4 if is_forex_or_comm else 2)
                    tp1 = round(c_close + (1.8 * atr if is_multiday else 0.9 * atr), 4 if is_forex_or_comm else 2)
                    tp2 = round(c_close + (3.5 * atr if is_multiday else 1.8 * atr), 4 if is_forex_or_comm else 2)

                    risk_per_share = max(round(c_close - sl, 4 if is_forex_or_comm else 2), 0.0001)
                    reward_t1 = round(tp1 - c_close, 4 if is_forex_or_comm else 2)
                    rrr_ratio = round(reward_t1 / risk_per_share, 2)
                    rec_qty = max(1, int(DEFAULT_RISK_PER_TRADE / risk_per_share))

                    grade = "💎 GRADE-A+ (INSTITUTIONAL)" if (rvol >= 2.2 or is_forex_or_comm) else "🔥 GRADE-A MOMENTUM"
                    display_name = NAME_MAP.get(ticker, ticker.replace(".NS", "").replace("-USD", ""))
                    currency = "₹" if ".NS" in ticker else ("$" if ("-USD" in ticker or "=F" in ticker) else "")

                    clean_sym = ticker.replace(".NS", "").replace("-USD", "").replace("=F", "").replace("=X", "")
                    tv_link = f"https://in.tradingview.com/chart/?symbol={clean_sym}"
                    screener_link = f"https://www.screener.in/company/{clean_sym}/" if ".NS" in ticker else f"https://finviz.com/quote.ashx?t={clean_sym}"

                    msg = (
                        f"🎯 *{grade}*\n\n"
                        f"🏷️ *Mode:* **{trade_mode}**\n"
                        f"⏳ *Horizon:* {holding}\n"
                        f"📈 *Asset:* **{display_name}**\n"
                        f"💵 *Entry:* {currency}{round(c_close, 4 if is_forex_or_comm else 2)}\n"
                        f"🛑 *Stop-Loss (SL):* {currency}{sl}\n"
                        f"🎯 *Target 1 (50% Book):* {currency}{tp1}\n"
                        f"🏆 *Target 2:* {currency}{tp2}\n\n"
                        f"⚖️ *Risk:Reward:* **1 : {rrr_ratio}**\n"
                        f"🧮 *Sizing Guide:* ~**{rec_qty} Units** (₹1,000 risk cap)\n"
                        f"📊 *Daily RSI:* {round(rsi, 1)} | *Price Action:* Breakout Validated ✅\n\n"
                        f"⚠️ *Risk Notice:* Automated alert. Always follow strict stop loss."
                    )

                    buttons = [
                        [
                            {"text": "📊 Open TradingView", "url": tv_link},
                            {"text": "🔍 Screener Analysis", "url": screener_link}
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
                        "type": trade_mode,
                        "currency": currency,
                        "tp1_alerted": False
                    }
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

    cache_data = load_json(CACHE_FILE, {"date": today_str, "tickers": []})
    sent_cache = set(cache_data.get("tickers", [])) if cache_data.get("date") == today_str else set()
    active_trades = load_json(ACTIVE_TRADES_FILE, {})
    daily_stats = load_json(DAILY_STATS_FILE, {})

    run_premarket_briefing_if_due(daily_stats, ist_now)
    active_trades = manage_active_trades(active_trades, daily_stats, today_str)

    full_universe = get_dynamic_universe()
    run_batch_market_scan(full_universe, sent_cache, active_trades)

    run_eod_summary_if_due(daily_stats, ist_now)

    save_json(CACHE_FILE, {"date": today_str, "tickers": list(sent_cache)})
    save_json(ACTIVE_TRADES_FILE, active_trades)
    save_json(DAILY_STATS_FILE, daily_stats)
