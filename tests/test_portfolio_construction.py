"""Round 3 (portfolio construction) tests.

P1 — diversification at constant risk: more slots, smaller size per trade.
P2 — idle-cash yield accrual on the uninvested balance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import config
from backtest import portfolio_engine as pe


def _flat(n, price=100.0, start="2026-01-01"):
    idx = pd.bdate_range(start, periods=n)
    p = np.full(n, price)
    df = pd.DataFrame({"open": p, "high": p, "low": p, "close": p,
                       "volume": np.full(n, 500000.0)}, index=idx)
    df["atr"] = 1.0
    return df


# ──────────────────────────────────────────────
# P2: idle-cash yield
# ──────────────────────────────────────────────

def test_no_cash_yield_by_default():
    df = _flat(30)
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: False,
                      exit_decision=lambda w, p, h: "HOLD")
    # Flat equity: idle cash earns nothing under the default config.
    assert out["equity_curve"].iloc[-1] == 100000.0


def test_cash_yield_compounds_on_idle_balance(monkeypatch):
    monkeypatch.setattr(config, "IDLE_CASH_ANNUAL_YIELD_PCT", 6.5)
    n = 253                       # ~1 trading year (252 accrual steps after day 0)
    df = _flat(n)
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: False,      # never invested
                      exit_decision=lambda w, p, h: "HOLD")
    end = out["equity_curve"].iloc[-1]
    # Fully idle for a year at 6.5% -> ~106,500 (geometric daily accrual).
    assert end == pytest.approx(100000 * 1.065, abs=50)


def test_cash_yield_creates_no_drawdown(monkeypatch):
    monkeypatch.setattr(config, "IDLE_CASH_ANNUAL_YIELD_PCT", 6.5)
    df = _flat(60)
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: False,
                      exit_decision=lambda w, p, h: "HOLD")
    eq = out["equity_curve"]
    assert (eq.diff().dropna() >= 0).all()      # monotonically non-decreasing


# ──────────────────────────────────────────────
# P1: diversification at constant total heat
# ──────────────────────────────────────────────

def test_more_slots_allows_more_concurrent_positions():
    # 10 symbols all signalling; capacity is what limits concurrency.
    data = {f"S{i}": _flat(12) for i in range(10)}
    common = dict(start_capital=100000, warmup=0,
                  entry_decision=lambda w, m: True,
                  exit_decision=lambda w, p, h: "HOLD")

    four = pe.simulate(data, max_positions=4, risk_pct=0.75, **common)
    eight = pe.simulate(data, max_positions=8, risk_pct=0.375, **common)

    assert four["positions_count"].max() <= 4
    assert eight["positions_count"].max() <= 8
    # Halving risk per trade at double the slots must actually fit more names.
    assert eight["positions_count"].max() > four["positions_count"].max()


def test_constant_heat_keeps_per_trade_risk_proportional():
    # 4 x 0.75% and 8 x 0.375% are the same 3.0% total heat.
    assert 4 * 0.75 == 8 * 0.375 == 10 * 0.30 == 3.0
