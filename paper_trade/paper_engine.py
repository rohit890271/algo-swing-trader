"""
Paper Trading Engine for Swing Trading Strategy.

Runs daily to simulate trades exactly as they would occur live,
using the same entry/exit logic and indicator vectorization used
in the historical backtest engine.

Saves state to JSON and CSV to persist across runs.
"""

from __future__ import annotations

import sys
import os
import time
import json
import csv
from datetime import datetime
import schedule

import pandas as pd

# Ensure the project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import (
    INITIAL_CAPITAL,
    WATCHLIST,
    PAPER_TRADE,
    MAX_OPEN_POSITIONS,
    POSITION_RISK_PCT,
    MAX_HOLD_DAYS,
    STRATEGY_MODE,
    STRICT_MIN_AVG_VOLUME,
    RELAXED_MIN_AVG_VOLUME,
)
from broker.zerodha_api import get_ohlcv_free
from strategy.indicators import enrich_with_indicators
from strategy.signals import check_entry_signal, check_exit_signal
from strategy.risk import calculate_atr_stop_loss, calculate_target, position_size

# ──────────────────────────────────────────────
# Setup Paths & State Management
# ──────────────────────────────────────────────

PAPER_DIR = os.path.join(os.path.dirname(__file__), "..", "paper_trades")
OPEN_POSITIONS_FILE = os.path.join(PAPER_DIR, "open_positions.json")
CLOSED_TRADES_FILE = os.path.join(PAPER_DIR, "closed_trades.csv")

os.makedirs(PAPER_DIR, exist_ok=True)


def load_open_positions() -> dict:
    if os.path.exists(OPEN_POSITIONS_FILE):
        with open(OPEN_POSITIONS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_open_positions(positions: dict) -> None:
    with open(OPEN_POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=4)


def log_closed_trade(trade: dict) -> None:
    file_exists = os.path.exists(CLOSED_TRADES_FILE)
    with open(CLOSED_TRADES_FILE, "a", newline="") as f:
        fieldnames = ["symbol", "entry_date", "exit_date", "entry_price", "exit_price", "pnl_pct", "exit_reason"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(trade)


def fetch_nifty_benchmark(days: int = 365) -> pd.DataFrame | None:
    """Fetch Nifty 50 benchmark to allow RS calculations."""
    try:
        import yfinance as yf
        raw = yf.download("^NSEI", period=f"{days}d", interval="1d", auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })[["open", "high", "low", "close", "volume"]].dropna()
        return df
    except Exception as e:
        print(f"  [!] Could not fetch Nifty 50: {e}")
        return None


# ──────────────────────────────────────────────
# Core Engine
# ──────────────────────────────────────────────

def run_daily_job():
    if not PAPER_TRADE:
        print("\n[ERROR] PAPER_TRADE is False in config.py. Refusing to run paper engine.")
        return

    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{today_str}] Waking up paper trading engine...")
    print(f"Strategy Mode: {STRATEGY_MODE}")

    positions = load_open_positions()
    
    today_entries = 0
    today_exits = 0
    total_realized_pnl = 0.0

    print("Fetching Nifty 50 benchmark...")
    nifty_df = fetch_nifty_benchmark(days=365)
    
    # We'll cache stock data during the run so we don't fetch twice 
    # (once for exit check, once for entry check)
    stock_cache = {}

    def get_stock_data(symbol: str) -> pd.DataFrame | None:
        if symbol in stock_cache:
            return stock_cache[symbol]
        try:
            df = get_ohlcv_free(symbol, days=365)
            if df.empty or len(df) < 50:
                return None

            # Apply volume filter based on strategy mode
            min_volume = STRICT_MIN_AVG_VOLUME if STRATEGY_MODE == "STRICT" else RELAXED_MIN_AVG_VOLUME
            avg_vol_20 = df["volume"].tail(20).mean()
            if avg_vol_20 < min_volume:
                return None

            df = enrich_with_indicators(df)
            stock_cache[symbol] = df
            return df
        except Exception:
            return None

    # 1. CHECK EXITS FOR OPEN POSITIONS
    exited_symbols = []
    
    for symbol, pos in positions.items():
        df = get_stock_data(symbol)
        if df is None:
            continue
            
        reason = check_exit_signal(
            df=df,
            entry_price=pos["entry_price"],
            entry_date=pos["entry_date"],
            stop_loss=pos["stop_loss"],
            target=pos["target"],
            max_hold_days=MAX_HOLD_DAYS,
            partial_taken=pos.get("partial_taken", False),
        )
        
        latest_date = str(df.index[-1].date())
        latest_close = float(df["close"].iloc[-1])

        if reason == "PARTIAL_EXIT_5PCT":
            # Book 50% profit
            pnl_pct = ((latest_close - pos["entry_price"]) / pos["entry_price"]) * 100.0
            total_realized_pnl += pnl_pct
            
            pos["partial_taken"] = True
            pos["qty"] = max(1, pos["qty"] // 2)
            pos["stop_loss"] = pos["entry_price"] # Move stop to breakeven
            
            trade_log = {
                "symbol": symbol,
                "entry_date": pos["entry_date"],
                "exit_date": latest_date,
                "entry_price": round(pos["entry_price"], 2),
                "exit_price": round(latest_close, 2),
                "pnl_pct": round(pnl_pct, 2),
                "exit_reason": reason
            }
            log_closed_trade(trade_log)
            print(f"  [PARTIAL EXIT] {symbol} @ {latest_close:.2f} | PNL: +{pnl_pct:.2f}%")
            
        elif reason != "HOLD":
            # Full Exit
            pnl_pct = ((latest_close - pos["entry_price"]) / pos["entry_price"]) * 100.0
            total_realized_pnl += pnl_pct
            
            trade_log = {
                "symbol": symbol,
                "entry_date": pos["entry_date"],
                "exit_date": latest_date,
                "entry_price": round(pos["entry_price"], 2),
                "exit_price": round(latest_close, 2),
                "pnl_pct": round(pnl_pct, 2),
                "exit_reason": reason
            }
            log_closed_trade(trade_log)
            exited_symbols.append(symbol)
            today_exits += 1
            print(f"  [EXIT] {symbol} @ {latest_close:.2f} | Reason: {reason} | PNL: {pnl_pct:+.2f}%")

    # Remove fully exited symbols
    for s in exited_symbols:
        del positions[s]

    # 2. CHECK ENTRIES & BUILD SCAN LOG
    scan_results = []
    import re
    
    print(f"\nScanning {len(WATCHLIST)} stocks for entries/rejections...")
    
    for symbol in WATCHLIST:
        df = get_stock_data(symbol)
        if df is None:
            continue
            
        result = check_entry_signal(df, nifty_df=nifty_df, strategy_mode=STRATEGY_MODE)
        
        latest_close = float(df["close"].iloc[-1])
        latest_rsi = float(df.get("rsi", pd.Series([0])).iloc[-1])
        latest_adx = float(df.get("adx", pd.Series([0])).iloc[-1])
        
        high_10d = float(df.get("high_10d", pd.Series([0])).iloc[-1])
        pullback_pct = ((high_10d - latest_close) / high_10d) * 100.0 if high_10d > 0 else 0.0
        
        vol = float(df["volume"].iloc[-1])
        vol_avg = float(df.get("vol_avg_5d", pd.Series([0])).iloc[-1])
        vol_ok = "Yes" if vol > vol_avg else "No"
        
        if result["signal"]:
            signal_label = "ENTRY"
            fail_detail = ""
            pass_count = 9
        else:
            signal_label = "FAIL_UNKNOWN"
            fail_detail = ""
            pass_count = 0
            
            for line in result["reason"].split("\n"):
                if "[PASS]" in line:
                    pass_count += 1
                elif "[FAIL]" in line and signal_label == "FAIL_UNKNOWN":
                    if "EMA-50 & EMA-200" in line:
                        signal_label = "FAIL_TREND"
                        fail_detail = "(Below EMAs)"
                    elif "EMA-20" in line and "EMA-50" in line:
                        signal_label = "FAIL_MOMENTUM"
                        fail_detail = "(Fast EMA < Med EMA)"
                    elif "Pullback" in line:
                        signal_label = "FAIL_PULLBACK"
                        match = re.search(r"Pullback ([-0-9.]+)%", line)
                        pct = match.group(1) if match else "0"
                        fail_detail = f"(only {pct}%, need 5%)"
                    elif "RSI" in line:
                        signal_label = "FAIL_RSI"
                        fail_detail = f"(RSI={latest_rsi:.0f}, need 42+)"
                    elif "volume" in line or "Today vol" in line:
                        signal_label = "FAIL_VOLUME"
                        fail_detail = "(Volume rules failed)"
                    elif "Bullish candle" in line:
                        signal_label = "FAIL_CANDLE"
                        fail_detail = "(Bearish today)"
                    elif "1-week return" in line:
                        signal_label = "FAIL_MOMENTUM"
                        fail_detail = "(Weekly return < -5%)"
                    elif "1 pullback day" in line:
                        signal_label = "FAIL_SETUP"
                        fail_detail = "(No pullback yesterday)"
                    elif "ADX" in line:
                        signal_label = "FAIL_ADX"
                        fail_detail = f"(ADX={latest_adx:.0f}, need 18+)"

        scan_results.append({
            "date": str(df.index[-1].date()),
            "symbol": symbol,
            "close": round(latest_close, 2),
            "rsi": round(latest_rsi, 2),
            "adx": round(latest_adx, 2),
            "pullback_pct": round(pullback_pct, 2),
            "volume_ok": vol_ok,
            "signal": signal_label,
            "fail_detail": fail_detail,
            "pass_count": pass_count
        })
        
        # Only simulate entry if capacity allows
        if result["signal"] and symbol not in positions and len(positions) < MAX_OPEN_POSITIONS:
                latest_date = str(df.index[-1].date())
                
                # Risk calcs
                atr_val = df["atr"].iloc[-1]
                stop_loss = calculate_atr_stop_loss(latest_close, atr_value=atr_val)
                target = calculate_target(latest_close, target_pct=0.08)
                
                try:
                    qty = position_size(
                        capital=INITIAL_CAPITAL, 
                        entry_price=latest_close, 
                        stop_loss_price=stop_loss, 
                        risk_pct=POSITION_RISK_PCT / 100.0
                    )
                except ValueError:
                    qty = 1 # Fallback if math fails
                
                if qty <= 0:
                    continue # Skip if risk is too high to buy even 1 share
                    
                positions[symbol] = {
                    "entry_date": latest_date,
                    "entry_price": round(latest_close, 2),
                    "stop_loss": stop_loss,
                    "target": target,
                    "qty": qty,
                    "partial_taken": False
                }
                
                today_entries += 1
                sl_pct = ((latest_close - stop_loss) / latest_close) * 100.0
                print(f"  [ENTRY] {symbol} @ {latest_close:.2f} | Qty: {qty} | SL: {stop_loss:.2f} (-{sl_pct:.1f}%)")

    # Save state
    save_open_positions(positions)
    
    # Save daily scan log
    DAILY_SCAN_LOG_FILE = os.path.join(PAPER_DIR, "daily_scan_log.csv")
    if scan_results:
        keys = ["date", "symbol", "close", "rsi", "adx", "pullback_pct", "volume_ok", "signal"]
        file_exists = os.path.exists(DAILY_SCAN_LOG_FILE)
        with open(DAILY_SCAN_LOG_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            if not file_exists:
                writer.writeheader()
            for row in scan_results:
                writer.writerow({k: row[k] for k in keys})
    
    # 3. PRINT DASHBOARD
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"\n   =======================================")
    print(f"   [DASHBOARD] PAPER TRADE — {date_str}")
    print(f"   =======================================")
    print(f"   Open Positions : {len(positions)}")
    print(f"   Today Entries  : {today_entries}")
    print(f"   Today Exits    : {today_exits}")
    print(f"   Total P&L      : {total_realized_pnl:+.2f}%")
    print(f"   =======================================")
    print(f"   [SCAN] CLOSEST TO ENTRY (Top 5)")
    print(f"   =======================================")
    
    failed_scans = [r for r in scan_results if r["signal"] != "ENTRY"]
    failed_scans.sort(key=lambda x: x["pass_count"], reverse=True)
    
    for row in failed_scans[:5]:
        print(f"   {row['symbol'].ljust(8)} - Failed: {row['signal']} {row['fail_detail']}")
    
    print(f"   =======================================\n")


# ──────────────────────────────────────────────
# Application Entry
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("Executing immediate paper-trade run...")
    run_daily_job()
    
    print("\nStarting daily schedule. Engine will run at 09:20 AM IST every day.")
    schedule.every().day.at("09:20", "Asia/Kolkata").do(run_daily_job)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nShutting down paper trading engine.")
