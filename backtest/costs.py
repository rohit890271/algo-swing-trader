# backtest/costs.py
"""Pure trading-cost model.

Costs are expressed as a fraction of traded notional and charged on both
the entry and the exit leg of a round-trip trade.  Values come from
``config`` (``COMMISSION_PCT`` brokerage+charges, ``SLIPPAGE_PCT`` estimated
slippage), each a *percent* number (0.03 == 0.03%).
"""
from __future__ import annotations

from config import COMMISSION_PCT, SLIPPAGE_PCT


def one_side_cost_pct() -> float:
    """Cost of a single leg as a fraction of notional."""
    return (COMMISSION_PCT + SLIPPAGE_PCT) / 100.0


def round_trip_cost_pct() -> float:
    """Total entry+exit cost as a fraction of notional."""
    return one_side_cost_pct() * 2.0


def trade_cost(entry_price: float, exit_price: float, qty: int) -> float:
    """Absolute cost (INR) of a round-trip: entry notional + exit notional, each charged one side."""
    side = one_side_cost_pct()
    return round((entry_price * qty * side) + (exit_price * qty * side), 4)
