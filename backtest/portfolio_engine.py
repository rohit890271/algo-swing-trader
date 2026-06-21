"""Pure, date-driven portfolio backtest engine.

The simulator trades a shared capital account across the whole universe,
respecting a maximum concurrent position count.  It is deliberately free of
network I/O: it consumes a ``{symbol: enriched OHLCV DataFrame}`` dict and
returns a trade log, an equity curve, and a daily position-count series.

Fill model (honest, no look-ahead):
  * Entry signals evaluated on the CLOSE of day t fill at the OPEN of day t+1.
  * Stop-loss / target are resolved intrabar against each day's high/low
    (gap-adjusted to the open).  [Added in Task 4.]
  * Discretionary exit signals (momentum/RSI/time/reversal) fill at the next
    open.  [Added in Task 4.]

Decision functions are injectable for testing.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from config import (
    INITIAL_CAPITAL, MAX_OPEN_POSITIONS, POSITION_RISK_PCT, MAX_HOLD_DAYS,
    STRATEGY_MODE,
)
from strategy.signals import check_entry_signal, check_exit_signal
from strategy.risk import calculate_atr_stop_loss, calculate_target, position_size
from backtest.costs import one_side_cost_pct

TRADE_COLUMNS = [
    "symbol", "entry_date", "exit_date", "entry_price", "exit_price",
    "qty", "gross_pnl", "cost", "net_pnl", "net_pnl_pct", "exit_reason",
]


def _default_entry_decision(window: pd.DataFrame, mode: str) -> bool:
    return check_entry_signal(window, strategy_mode=mode)["signal"]


def _default_exit_decision(window: pd.DataFrame, position: dict, max_hold: int) -> str:
    return check_exit_signal(
        window, entry_price=position["entry_price"], entry_date=position["entry_date"],
        stop_loss=position["stop_loss"], target=position["target"],
        max_hold_days=max_hold, partial_taken=position.get("partial_taken", False),
    )


def _setup_strength(window: pd.DataFrame) -> float:
    """Deterministic ranking key when more candidates than open slots exist.

    Rank by ADX (trend strength) of the latest bar, descending.  Falls back to
    0.0 if ADX is unavailable.
    """
    if "adx" in window.columns:
        val = window["adx"].iloc[-1]
        return float(val) if pd.notna(val) else 0.0
    return 0.0


def simulate(price_data: dict[str, pd.DataFrame], start_capital: float = INITIAL_CAPITAL,
             strategy_mode: str = STRATEGY_MODE, max_positions: int = MAX_OPEN_POSITIONS,
             risk_pct: float = POSITION_RISK_PCT, warmup: int = 200,
             entry_decision=None, exit_decision=None,
             nifty_df: pd.DataFrame | None = None) -> dict:
    """Run the portfolio simulation. Returns trade_log / equity_curve / positions_count."""
    entry_decision = entry_decision or _default_entry_decision
    exit_decision = exit_decision or _default_exit_decision
    side_cost = one_side_cost_pct()

    all_dates = sorted(set().union(*[df.index for df in price_data.values()])) \
        if price_data else []

    cash = float(start_capital)
    positions: dict[str, dict] = {}
    trades: list[dict] = []
    pending_entries: list[str] = []
    equity_records: dict = {}
    count_records: dict = {}
    debug_last_entry_price = None

    def current_equity(date) -> float:
        eq = cash
        for sym, pos in positions.items():
            df = price_data[sym]
            price = df.loc[date, "close"] if date in df.index else pos["entry_price"]
            eq += pos["qty"] * float(price)
        return eq

    for date in all_dates:
        # ---- Phase 1: fill queued entries at TODAY's open ----
        for sym in pending_entries:
            if sym in positions or len(positions) >= max_positions:
                continue
            df = price_data[sym]
            if date not in df.index:
                continue
            entry_price = float(df.loc[date, "open"])
            atr_val = float(df.loc[date, "atr"]) if "atr" in df.columns and pd.notna(df.loc[date, "atr"]) else 0.0
            if atr_val <= 0:
                continue
            stop = calculate_atr_stop_loss(entry_price, atr_value=atr_val)
            target = calculate_target(entry_price, target_pct=0.08)
            equity_now = current_equity(date)
            try:
                qty = position_size(equity_now, entry_price, stop, risk_pct / 100.0)
            except ValueError:
                continue
            # Cap by available cash (plus entry cost).
            affordable = int(cash / (entry_price * (1 + side_cost)))
            qty = min(qty, affordable)
            if qty <= 0:
                continue
            entry_cost = entry_price * qty * side_cost
            cash -= (entry_price * qty + entry_cost)
            positions[sym] = {
                "symbol": sym, "entry_date": date, "entry_price": entry_price,
                "qty": qty, "stop_loss": stop, "target": target,
                "partial_taken": False, "entry_cost": entry_cost,
            }
            debug_last_entry_price = entry_price
        pending_entries = []

        # ---- Phase 3: evaluate signals on TODAY's close, queue for next open ----
        if len(positions) < max_positions:
            candidates = []
            for sym, df in price_data.items():
                if sym in positions:
                    continue
                window = df.loc[:date]
                if len(window) <= warmup or window.index[-1] != date:
                    continue
                if entry_decision(window, strategy_mode):
                    candidates.append((sym, _setup_strength(window)))
            candidates.sort(key=lambda x: x[1], reverse=True)
            slots = max_positions - len(positions)
            pending_entries = [s for s, _ in candidates[:slots]]

        equity_records[date] = current_equity(date)
        count_records[date] = len(positions)

    return {
        "trade_log": pd.DataFrame(trades, columns=TRADE_COLUMNS),
        "equity_curve": pd.Series(equity_records, dtype=float),
        "positions_count": pd.Series(count_records, dtype=float),
        "_debug_last_entry_price": debug_last_entry_price,
    }
