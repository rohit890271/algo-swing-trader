"""Tests for performance-metric computation."""
from __future__ import annotations

import pandas as pd

from backtest import metrics


def _trade_log():
    # Two winners (+5%, +3%), one loser (-2%), net pnl already cost-adjusted.
    return pd.DataFrame([
        {"symbol": "A", "net_pnl": 500.0, "net_pnl_pct": 5.0},
        {"symbol": "B", "net_pnl": 300.0, "net_pnl_pct": 3.0},
        {"symbol": "C", "net_pnl": -200.0, "net_pnl_pct": -2.0},
    ])


def _equity_and_counts():
    idx = pd.bdate_range("2026-01-01", periods=5)
    equity = pd.Series([100000, 100500, 100800, 100600, 100600.0], index=idx)
    counts = pd.Series([0, 1, 2, 1, 0], index=idx)
    return equity, counts


def test_basic_counts_and_winrate():
    equity, counts = _equity_and_counts()
    m = metrics.compute_metrics(_trade_log(), equity, counts, start_capital=100000)
    assert m["total_trades"] == 3
    assert m["winners"] == 2
    assert m["losers"] == 1
    assert m["win_rate_pct"] == round(2 / 3 * 100, 2)


def test_profit_factor_and_expectancy_use_net():
    equity, counts = _equity_and_counts()
    m = metrics.compute_metrics(_trade_log(), equity, counts, start_capital=100000)
    # gross profit 800, gross loss 200 -> PF 4.0
    assert m["profit_factor"] == 4.0
    # expectancy = mean net_pnl_pct = (5+3-2)/3
    assert m["expectancy_pct"] == round((5 + 3 - 2) / 3, 2)


def test_drawdown_and_exposure():
    equity, counts = _equity_and_counts()
    m = metrics.compute_metrics(_trade_log(), equity, counts, start_capital=100000)
    # peak 100800 -> trough 100600 => dd = (100600-100800)/100800*100
    assert m["max_drawdown_pct"] == round(abs((100600 - 100800) / 100800 * 100), 2)
    # exposure: 3 of 5 days held >=1 position
    assert m["exposure_pct"] == 60.0


def test_haircut_scales_returns():
    base = {"total_return_pct": 50.0, "cagr_pct": 20.0}
    out = metrics.apply_haircut(base, haircut_pct=20.0)
    assert out["total_return_pct"] == 40.0
    assert out["cagr_pct"] == 16.0


def test_empty_log_is_safe():
    equity, counts = _equity_and_counts()
    m = metrics.compute_metrics(pd.DataFrame(), equity, counts, start_capital=100000)
    assert m["total_trades"] == 0
    assert m["profit_factor"] == 0.0


def test_mar_ratio_is_cagr_over_max_drawdown():
    equity, counts = _equity_and_counts()
    m = metrics.compute_metrics(_trade_log(), equity, counts, start_capital=100000)
    assert m["max_drawdown_pct"] > 0
    assert m["mar_ratio"] == round(m["cagr_pct"] / m["max_drawdown_pct"], 2)


def test_mar_ratio_inf_when_no_drawdown():
    idx = pd.bdate_range("2026-01-01", periods=5)
    rising = pd.Series([100000, 100100, 100200, 100300, 100400.0], index=idx)
    counts = pd.Series([1, 1, 1, 1, 1], index=idx)
    m = metrics.compute_metrics(pd.DataFrame(), rising, counts, start_capital=100000)
    assert m["mar_ratio"] == float("inf")
