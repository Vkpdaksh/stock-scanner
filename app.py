                            <div style="font-size: 11px; font-weight: 700; color: #555555; text-transform: uppercase;">
                                {clean_name}
                            </div>
                            <div style="font-size: 14px; font-weight: 800; color: #111111; margin: 2px 0;">
                                {curr:.1f}
                            </div>
                            <div style="font-size: 12px; font-weight: 700; color: {text_color};">
                                {icon} {pct:+.2f}%
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
            except Exception:
                pass
    except Exception:
        st.caption("Sector radar loading...")

# -------------------------------------------------------------
# 8. BROWSER AUDIO BEEP CHIME
# -------------------------------------------------------------
if has_sniper_alert:
    audio_chime = """
    <script>
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, audioCtx.currentTime);
        gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.6);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.6);
    } catch(e) {}
    </script>
    """
    components.html(audio_chime, height=0, width=0)

# -------------------------------------------------------------
# 9. METRIC CARDS ROW
# -------------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Universe Tracked", len(tickers))
with m2:
    st.metric("Active Breakouts", active_breakouts)
with m3:
    st.metric("Risk Budget", f"₹{risk_per_trade}")
with m4:
    st.metric("Execution Mode", execution_type)

st.markdown("---")

# -------------------------------------------------------------
# 10. MONITORING DATA TABLE
# -------------------------------------------------------------
if records:
    df_display = pd.DataFrame(records).drop(columns=["Ticker", "Size"])
    st.dataframe(df_display, use_container_width=True, hide_index=True)
else:
    st.info("No active breakout setups currently found in this asset pool.")

# -------------------------------------------------------------
# 11. DUAL EXECUTION DESK WITH CUSTOM PRICE ADJUSTMENT
# -------------------------------------------------------------
st.markdown("### ⚡ Order Execution Desk")
ord_col1, ord_col2, ord_col3, ord_col4 = st.columns([1.8, 1.2, 1.2, 1.8])
asset_names = [r["Asset"] for r in records] if records else []

with ord_col1:
    chosen_asset = st.selectbox("Contract / Asset:", asset_names if asset_names else ["None"])

selected_item = next((r for r in records if r["Asset"] == chosen_asset), None)
default_ltp = selected_item["LTP"] if selected_item else 100.0

with ord_col2:
    side = st.selectbox("Direction:", ["BUY", "SELL"])

with ord_col3:
    suggested_qty = selected_item["Size"] if selected_item else 1
    qty_input = st.number_input("Qty / Lots:", min_value=1, value=max(1, suggested_qty), step=1)

with ord_col4:
    custom_exec_price = st.number_input("Execution Price (₹):", min_value=0.01, value=float(default_ltp), step=0.05, format="%.2f")

st.write("")
if is_beginner or execution_type == "Paper Trading":
    if st.button("📥 Record Virtual Paper Trade at Custom Price", use_container_width=True):
        if selected_item:
            new_trade = {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "asset": chosen_asset,
                "type": side,
                "entry": custom_exec_price,
                "sl": selected_item["Stop Loss"],
                "tp1": selected_item["Target 1 (1:1)"],
                "tp2": selected_item["Target 2 (1:2)"],
                "qty": qty_input,
                "status": "OPEN"
            }
            paper_data["trades"].append(new_trade)
            save_json(PAPER_TRADES_FILE, paper_data)
            st.success(f"Virtual {side} Order Placed for {chosen_asset} at ₹{custom_exec_price}!")
            st.rerun()
        else:
            st.warning("Pehle koi valid asset select karein.")
else:
    if st.button("🚀 Fire to Angel One (Real Fund)", use_container_width=True):
        if selected_item:
            raw_sym = selected_item["Ticker"]
            exch = "NSE" if ".NS" in raw_sym or "^NSE" in raw_sym else "MCX"
            clean_sym = raw_sym.replace(".NS", "").replace("^", "")
            
            ok, msg = place_order_smartapi(
                symbol_token=clean_sym,
                trading_symbol=clean_sym,
                exchange=exch,
                qty=qty_input,
                transaction_type=side,
                price=custom_exec_price
            )
            if ok:
                st.success(msg)
            else:
                st.error(f"Execution failed: {msg}")
        else:
            st.warning("Asset select karein.")

# -------------------------------------------------------------
# 12. COMPLETED PAPER TRADE HISTORY LEDGER
# -------------------------------------------------------------
if closed_trades:
    with st.expander("📜 Completed Paper Trades Ledger", expanded=False):
        history_df = pd.DataFrame(closed_trades)
        st.dataframe(history_df, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# 13. INTERACTIVE TRADINGVIEW CANDLESTICK CHART
# -------------------------------------------------------------
st.markdown("### 📈 Interactive TradingView Live Chart")
if records and selected_item:
    raw_ticker = selected_item["Ticker"]
    if ".NS" in raw_ticker:
        sym = "NSE:" + raw_ticker.replace(".NS", "")
    elif raw_ticker == "^NSEI":
        sym = "NSE:NIFTY"
    elif raw_ticker == "^NSEBANK":
        sym = "NSE:BANKNIFTY"
    elif "=" in raw_ticker or "-USD" in raw_ticker:
        sym = raw_ticker.replace("-USD", "USD").replace("=F", "").replace("=X", "")
    else:
        sym = raw_ticker

    tv_code = f"""
    <div class="tradingview-widget-container" style="height:550px; width:100%;">
      <div id="tradingview_chart" style="height:550px;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": true,
        "symbol": "{sym}",
        "interval": "15",
        "timezone": "Asia/Kolkata",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "toolbar_bg": "#131722",
        "enable_publishing": false,
        "hide_side_toolbar": false,
        "allow_symbol_change": true,
        "container_id": "tradingview_chart"
      }}
      );
      </script>
    </div>
    """
    components.html(tv_code, height=560)
