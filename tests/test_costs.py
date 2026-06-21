# tests/test_costs.py
"""Tests for the pure trading-cost model."""
from __future__ import annotations

from backtest import costs


def test_one_side_cost_pct_matches_config():
    # COMMISSION_PCT=0.03 + SLIPPAGE_PCT=0.05 = 0.08% per side = 0.0008 fraction.
    assert costs.one_side_cost_pct() == 0.0008


def test_round_trip_is_two_sides():
    assert costs.round_trip_cost_pct() == 0.0016


def test_trade_cost_charges_both_legs():
    # 100 shares: entry 100 -> 10000 notional, exit 110 -> 11000 notional.
    # cost = (10000 + 11000) * 0.0008 = 16.8
    assert costs.trade_cost(entry_price=100.0, exit_price=110.0, qty=100) == 16.8
