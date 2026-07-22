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

import config as _cfg   # Phase 2 flags read dynamically (testable via monkeypatch)
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
from strategy.indicators import enrich_with_indicators, ema
from strategy.signals import check_entry_signal, check_exit_signal
from strategy.risk import calculate_atr_stop_loss, calculate_target, position_size
from backtest.costs import one_side_cost_pct
from backtest.portfolio_engine import (
    ratcheted_trailing_stop, _close_position, _book_partial,
    DISCRETIONARY_EXITS, TRADE_COLUMNS,
)

# ──────────────────────────────────────────────
# Setup Paths & State Management
# ──────────────────────────────────────────────

PAPER_DIR = os.path.join(os.path.dirname(__file__), "..", "paper_trades")
OPEN_POSITIONS_FILE = os.path.join(PAPER_DIR, "open_positions.json")
CLOSED_TRADES_FILE = os.path.join(PAPER_DIR, "closed_trades.csv")
PORTFOLIO_STATE_FILE = os.path.join(PAPER_DIR, "portfolio_state.json")
PENDING_FILE = os.path.join(PAPER_DIR, "pending_orders.json")
EQUITY_CURVE_FILE = os.path.join(PAPER_DIR, "equity_curve.csv")
DAILY_SCAN_LOG_FILE = os.path.join(PAPER_DIR, "daily_scan_log.csv")

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


def load_portfolio_state(path: str | None = None) -> dict:
    """Load the running forward-test book: marked equity, free cash, realized P&L.

    ``cash`` backfills from ``equity`` for state files written before
    mark-to-market existed (at that point the book was tracked flat, so the two
    were the same number).

    ``path`` resolves at call time, not import time, so redirecting the
    module-level artifact paths actually takes effect.
    """
    path = path or PORTFOLIO_STATE_FILE
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            equity = float(data.get("equity", INITIAL_CAPITAL))
            return {"equity": equity,
                    "cash": float(data.get("cash", equity)),
                    "realized_pnl": float(data.get("realized_pnl", 0.0))}
        except (json.JSONDecodeError, ValueError):
            pass
    return {"equity": float(INITIAL_CAPITAL), "cash": float(INITIAL_CAPITAL),
            "realized_pnl": 0.0}


def save_portfolio_state(state: dict, path: str | None = None) -> None:
    with open(path or PORTFOLIO_STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)


def load_pending(path: str | None = None) -> dict:
    """Load the next-open order queues, defaulting to empty."""
    path = path or PENDING_FILE
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return {"entries": data.get("entries", {}) or {},
                    "exits": data.get("exits", {}) or {}}
        except json.JSONDecodeError:
            pass
    return {"entries": {}, "exits": {}}


def save_pending(pending: dict, path: str | None = None) -> None:
    with open(path or PENDING_FILE, "w") as f:
        json.dump(pending, f, indent=4)


def should_fill_pending(signal_date: str, bar_date: str) -> bool:
    """True once a bar *newer* than the signal bar has printed.

    Signals are generated on a bar's close and filled at the **next** bar's
    open, mirroring the backtest.  Re-running the engine on the same bar (or on
    a stale download) must not fill anything, because the open we would fill at
    has not happened yet.
    """
    return bar_date > signal_date


def mark_to_market(cash: float, positions: dict, prices: dict) -> float:
    """Account equity: free cash plus open positions at last traded price.

    Symbols missing from ``prices`` (failed download) contribute nothing rather
    than a guessed value — a data outage must not invent equity.
    """
    held = sum(pos["qty"] * prices[sym]
               for sym, pos in positions.items() if sym in prices)
    return round(cash + held, 2)


def entry_cost(price: float, qty: int) -> float:
    """One-leg trading cost (INR) on ``qty`` shares at ``price``."""
    return round(price * qty * one_side_cost_pct(), 4)


def size_for_equity(equity: float, entry_price: float, stop_loss: float,
                    risk_pct: float = POSITION_RISK_PCT) -> int:
    """Shares to buy, risking ``risk_pct``% of *current* equity to the stop.

    Returns 0 for degenerate risk (stop at or above entry) rather than falling
    back to an arbitrary quantity — an unsized setup is simply skipped.
    """
    try:
        return position_size(capital=equity, entry_price=entry_price,
                             stop_loss_price=stop_loss, risk_pct=risk_pct / 100.0)
    except (ValueError, ZeroDivisionError):
        return 0


def append_equity_point(path: str, date_str: str, equity: float) -> None:
    """Record one mark-to-market point, replacing any existing row for that bar.

    Re-running the engine on the same bar overwrites rather than appends, so the
    daily-return series stays one-point-per-day (Sharpe depends on it).
    """
    rows: dict[str, float] = {}
    if os.path.exists(path):
        with open(path, "r", newline="") as f:
            for row in csv.DictReader(f):
                rows[row["date"]] = float(row["equity"])
    rows[date_str] = round(float(equity), 2)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "equity"])
        writer.writeheader()
        for d in sorted(rows):
            writer.writerow({"date": d, "equity": rows[d]})


def load_equity_curve(path: str | None = None) -> pd.Series:
    """The forward-test equity curve as a date-indexed Series (empty if absent)."""
    path = path or EQUITY_CURVE_FILE
    if not os.path.exists(path):
        return pd.Series(dtype=float)
    df = pd.read_csv(path, parse_dates=["date"])
    if df.empty:
        return pd.Series(dtype=float)
    return pd.Series(df["equity"].astype(float).values,
                     index=pd.DatetimeIndex(df["date"]))


def log_closed_trade(trade: dict) -> None:
    """Append one booked trade in the backtest's ``TRADE_COLUMNS`` schema.

    Same columns as ``backtest.portfolio_engine`` so ``backtest.metrics`` can
    score the forward test with the identical code path as the backtest.
    """
    file_exists = os.path.exists(CLOSED_TRADES_FILE)
    with open(CLOSED_TRADES_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: trade.get(k) for k in TRADE_COLUMNS})


def load_closed_trades(path: str | None = None) -> pd.DataFrame:
    """Booked forward trades as a DataFrame (empty frame if none yet)."""
    path = path or CLOSED_TRADES_FILE
    if not os.path.exists(path):
        return pd.DataFrame(columns=TRADE_COLUMNS)
    df = pd.read_csv(path)
    return df if not df.empty else pd.DataFrame(columns=TRADE_COLUMNS)


def is_market_regime_ok(nifty_df: pd.DataFrame | None,
                        ema_period: int | None = None) -> bool:
    """True when the index closes above its regime EMA (H1 market filter).

    Fails **open** (returns True) when the benchmark is missing or too short
    to compute the EMA, so a data outage cannot silently gate the strategy —
    the regime filter only applies when the regime is actually measurable.
    """
    if nifty_df is None or len(nifty_df) == 0:
        return True
    period = ema_period if ema_period is not None else _cfg.REGIME_EMA_PERIOD
    closes = nifty_df["close"].astype(float)   # TA-Lib requires float64
    bench_ema = ema(closes, period).iloc[-1]
    if pd.isna(bench_ema):
        return True
    return bool(closes.iloc[-1] > bench_ema)


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
    pending = load_pending()
    portfolio_state = load_portfolio_state()
    cash = portfolio_state["cash"]
    equity_for_sizing = portfolio_state["equity"]
    side_cost = one_side_cost_pct()

    booked: list[dict] = []          # trades closed this run
    today_entries = 0
    today_exits = 0

    print("Fetching Nifty 50 benchmark...")
    nifty_df = fetch_nifty_benchmark(days=500)   # enough history for the regime EMA

    # H1: market regime gate — exits still process, but no new entries open
    # while the index is below its regime EMA.
    regime_ok = True
    if _cfg.REGIME_FILTER_ENABLED:
        regime_ok = is_market_regime_ok(nifty_df)
        if not regime_ok:
            print(f"  [REGIME] Nifty below EMA-{_cfg.REGIME_EMA_PERIOD} "
                  f"-- no new entries today.")

    trailing = _cfg.TRAILING_EXIT_ENABLED

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

    # Establish the newest completed bar seen across the book + watchlist.
    # Signals fire on this bar's close; fills land on the NEXT bar's open.
    def _latest_date(df: pd.DataFrame) -> str:
        return str(df.index[-1].date())

    held_data = {s: get_stock_data(s) for s in list(positions) + list(pending["exits"])}
    held_data = {s: d for s, d in held_data.items() if d is not None}
    pending_data = {s: get_stock_data(s) for s in pending["entries"]}
    pending_data = {s: d for s, d in pending_data.items() if d is not None}

    known_dates = [_latest_date(d) for d in list(held_data.values()) + list(pending_data.values())]
    bar_date = max(known_dates) if known_dates else None

    # ── PHASE 1a: fill queued discretionary exits at this bar's OPEN ──
    for symbol, order in list(pending["exits"].items()):
        df = held_data.get(symbol)
        if df is None or symbol not in positions:
            pending["exits"].pop(symbol, None)
            continue
        if not should_fill_pending(order["signal_date"], _latest_date(df)):
            continue
        open_px = float(df["open"].iloc[-1])
        cash += _close_position(positions, booked, symbol, open_px,
                                _latest_date(df), order["reason"], side_cost)
        pending["exits"].pop(symbol, None)
        today_exits += 1
        print(f"  [EXIT] {symbol} @ open {open_px:.2f} | Reason: {order['reason']}")

    # ── PHASE 1b: fill queued entries at this bar's OPEN ──
    for symbol, order in list(pending["entries"].items()):
        df = pending_data.get(symbol)
        if df is None:
            pending["entries"].pop(symbol, None)
            continue
        if not should_fill_pending(order["signal_date"], _latest_date(df)):
            continue
        pending["entries"].pop(symbol, None)
        if symbol in positions or len(positions) >= MAX_OPEN_POSITIONS:
            continue

        open_px = float(df["open"].iloc[-1])
        atr_val = df["atr"].iloc[-1]
        stop_loss = calculate_atr_stop_loss(open_px, atr_value=atr_val)
        qty = size_for_equity(equity_for_sizing, open_px, stop_loss)
        if qty <= 0:
            continue
        cost = entry_cost(open_px, qty)
        if cash < (open_px * qty) + cost:
            print(f"  [SKIP] {symbol} -- insufficient cash for {qty} @ {open_px:.2f}")
            continue

        cash -= (open_px * qty) + cost
        positions[symbol] = {
            "entry_date": _latest_date(df),
            "entry_price": round(open_px, 2),
            "stop_loss": stop_loss,
            "target": calculate_target(open_px, target_pct=0.08),
            "qty": qty,
            "partial_taken": False,
            "entry_cost": cost,
        }
        today_entries += 1
        sl_pct = ((open_px - stop_loss) / open_px) * 100.0
        print(f"  [ENTRY] {symbol} @ open {open_px:.2f} | Qty: {qty} "
              f"| SL: {stop_loss:.2f} (-{sl_pct:.1f}%)")

    # Refresh data for anything now held that we have not fetched yet.
    for symbol in positions:
        if symbol not in held_data:
            d = get_stock_data(symbol)
            if d is not None:
                held_data[symbol] = d

    # ── PHASE 2: intrabar stop / target on this bar, stop checked first ──
    for symbol in list(positions):
        df = held_data.get(symbol)
        if df is None:
            continue
        pos = positions[symbol]
        bar = df.iloc[-1]
        low, high = float(bar["low"]), float(bar["high"])

        if low <= pos["stop_loss"]:
            cash += _close_position(positions, booked, symbol, pos["stop_loss"],
                                    _latest_date(df), "STOP_LOSS", side_cost)
            today_exits += 1
            print(f"  [EXIT] {symbol} @ {pos['stop_loss']:.2f} | Reason: STOP_LOSS")
        elif not trailing and high >= pos["target"]:
            cash += _close_position(positions, booked, symbol, pos["target"],
                                    _latest_date(df), "TARGET", side_cost)
            today_exits += 1
            print(f"  [EXIT] {symbol} @ {pos['target']:.2f} | Reason: TARGET")

    # ── PHASE 2b: partial booking + trailing ratchet on this bar's close ──
    for symbol in list(positions):
        df = held_data.get(symbol)
        if df is None:
            continue
        pos = positions[symbol]
        latest_close = float(df["close"].iloc[-1])

        if not pos.get("partial_taken", False) and \
                latest_close >= pos["entry_price"] * 1.05:
            cash += _book_partial(positions, booked, symbol, latest_close,
                                  _latest_date(df), side_cost)
            print(f"  [PARTIAL EXIT] {symbol} @ {latest_close:.2f}")

        if trailing and latest_close >= pos["entry_price"] * _cfg.TRAILING_ACTIVATION_GAIN:
            atr_now = float(df["atr"].iloc[-1]) if "atr" in df.columns \
                and pd.notna(df["atr"].iloc[-1]) else 0.0
            new_stop = ratcheted_trailing_stop(pos["stop_loss"], latest_close, atr_now)
            if new_stop > pos["stop_loss"]:
                pos["stop_loss"] = round(new_stop, 2)

    # ── PHASE 3: queue discretionary exits for the next open ──
    for symbol in list(positions):
        df = held_data.get(symbol)
        if df is None or symbol in pending["exits"]:
            continue
        pos = positions[symbol]
        reason = check_exit_signal(
            df=df,
            entry_price=pos["entry_price"],
            entry_date=pos["entry_date"],
            stop_loss=pos["stop_loss"],
            # H2: no fixed profit cap when trailing -- the ratcheted stop exits.
            target=float("inf") if trailing else pos["target"],
            max_hold_days=_cfg.TRAILING_MAX_HOLD_DAYS if trailing else MAX_HOLD_DAYS,
            partial_taken=pos.get("partial_taken", False),
        )
        if trailing and reason == "MOMENTUM_FADE":
            reason = "HOLD"   # H2: the trailing stop, not RSI dips, ends winners
        if reason in DISCRETIONARY_EXITS:
            pending["exits"][symbol] = {"signal_date": _latest_date(df), "reason": reason}
            print(f"  [QUEUED EXIT] {symbol} -- {reason} at next open")

    # ── PHASE 4: scan for entry signals, queue them for the next open ──
    scan_results = []
    candidates: list[tuple[float, str]] = []   # (setup strength, symbol)
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

            # Split reason text into individual segments.
            # The volume condition emits "[FAIL] ... | [PASS] ..." on ONE line
            # separated by " | ", so we must split on pipe before checking tags.
            segments: list[str] = []
            for raw_line in result["reason"].split("\n"):
                segments.extend(raw_line.split(" | "))

            for seg in segments:
                seg = seg.strip()
                if "[PASS]" in seg:
                    pass_count += 1
                elif "[FAIL]" in seg and signal_label == "FAIL_UNKNOWN":
                    # Trend: price vs EMA-50 (no EMA-20 involvement)
                    if "EMA-50" in seg and "EMA-20" not in seg:
                        signal_label = "FAIL_TREND"
                        fail_detail = "(Price below EMA)"
                    # Momentum: EMA-20 not above EMA-50
                    elif "EMA-20" in seg and "EMA-50" in seg:
                        signal_label = "FAIL_MOMENTUM"
                        fail_detail = "(Fast EMA < Med EMA)"
                    # Pullback range
                    elif "Pullback" in seg:
                        signal_label = "FAIL_PULLBACK"
                        match = re.search(r"Pullback ([\d.]+)%", seg)
                        need_match = re.search(r"need ([\d.]+-[\d.]+)%", seg)
                        pct  = match.group(1)      if match      else "0"
                        need = need_match.group(1) if need_match else "?"
                        fail_detail = f"(only {pct}%, need {need}%)"
                    # RSI outside allowed range
                    elif "RSI" in seg and "range" in seg:
                        signal_label = "FAIL_RSI"
                        need_match = re.search(r"([\d.]+-[\d.]+) range", seg)
                        need = need_match.group(1) if need_match else "?"
                        fail_detail = f"(RSI={latest_rsi:.0f}, need {need})"
                    # Volume: declining vol dry-up OR today < 5-day avg
                    elif "declining volume" in seg or "Today vol" in seg:
                        signal_label = "FAIL_VOLUME"
                        if "Today vol" in seg:
                            fail_detail = "(Today vol < 5-day avg)"
                        else:
                            fail_detail = "(Vol dry-up not confirmed)"
                    # Bearish candle
                    elif "Bullish candle" in seg or "candle" in seg.lower():
                        signal_label = "FAIL_CANDLE"
                        fail_detail = "(Bearish candle today)"
                    # Freefall / 1-week return
                    elif "1-week return" in seg:
                        signal_label = "FAIL_FREEFALL"
                        fail_detail = "(Weekly return < -5%)"
                    # No pullback day before entry
                    elif "pullback day" in seg:
                        signal_label = "FAIL_SETUP"
                        fail_detail = "(No pullback yesterday)"
                    # ADX below threshold
                    elif "ADX" in seg:
                        signal_label = "FAIL_ADX"
                        need_match = re.search(r"<= ([\d.]+)", seg)
                        need = need_match.group(1) if need_match else "?"
                        fail_detail = f"(ADX={latest_adx:.0f}, need >{need})"




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
        
        # Queue the entry for the next open (H1 regime gates new longs only).
        if result["signal"] and regime_ok and symbol not in positions \
                and symbol not in pending["entries"]:
            candidates.append((latest_adx, symbol))

    # More candidates than free slots: rank by trend strength (ADX), same
    # deterministic tie-break the backtest uses.
    free_slots = max(0, MAX_OPEN_POSITIONS - len(positions))
    candidates.sort(reverse=True)
    for _, symbol in candidates[:free_slots]:
        df = stock_cache[symbol]
        pending["entries"][symbol] = {"signal_date": str(df.index[-1].date())}
        print(f"  [QUEUED ENTRY] {symbol} -- fills at next open")

    # ── Mark the book to market and persist state ──
    prices = {s: float(d["close"].iloc[-1]) for s, d in stock_cache.items()}
    equity = mark_to_market(cash, positions, prices)
    realized_this_run = sum(t["net_pnl"] for t in booked)
    portfolio_state = {
        "equity": equity,
        "cash": round(cash, 2),
        "realized_pnl": round(portfolio_state["realized_pnl"] + realized_this_run, 2),
    }

    for trade in booked:
        log_closed_trade(trade)

    save_open_positions(positions)
    save_pending(pending)
    save_portfolio_state(portfolio_state)
    if bar_date is None and prices:
        bar_date = max(str(d.index[-1].date()) for d in stock_cache.values())
    if bar_date:
        append_equity_point(EQUITY_CURVE_FILE, bar_date, equity)

    # Save daily scan log
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
    print(f"   Bar Date       : {bar_date or 'n/a'}")
    print(f"   Open Positions : {len(positions)} / {MAX_OPEN_POSITIONS}")
    print(f"   Queued Entries : {len(pending['entries'])}")
    print(f"   Queued Exits   : {len(pending['exits'])}")
    print(f"   Filled Entries : {today_entries}")
    print(f"   Filled Exits   : {today_exits}")
    print(f"   Booked P&L     : {realized_this_run:+,.2f} (this run, net of costs)")
    print(f"   Free Cash      : {cash:,.2f}")
    print(f"   Forward Equity : {equity:,.2f} "
          f"(realized {portfolio_state['realized_pnl']:+,.2f})")
    ret_pct = (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0
    print(f"   Total Return   : {ret_pct:+.2f}%")
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
