"""Tests for the Phase 2 hypothesis wiring.

H1 — market regime filter (regime_ok map gates entry queueing)
H2 — trailing exits let winners run past the old fixed 8% target
H3 — relative-strength entry condition vs the Nifty benchmark
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
from backtest import portfolio_engine as pe
from backtest.run_portfolio import build_regime_map
from strategy.signals import check_entry_signal


def _frame(rows, start="2026-01-01"):
    """rows: list of (open, high, low, close). Fixed volume, atr=1.0 attached."""
    idx = pd.bdate_range(start, periods=len(rows))
    arr = np.array(rows, dtype=float)
    df = pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2],
                       "close": arr[:, 3], "volume": np.full(len(rows), 500000.0)},
                      index=idx)
    df["atr"] = 1.0
    return df


# ──────────────────────────────────────────────
# H1: market regime filter
# ──────────────────────────────────────────────

def test_regime_map_blocks_all_entries():
    df = _frame([(100, 100, 100, 100)] * 6)
    blocked = {d: False for d in df.index}
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: True,
                      exit_decision=lambda w, p, h: "HOLD",
                      regime_ok=blocked)
    assert out["positions_count"].max() == 0
    assert out["trade_log"].empty


def test_regime_map_allows_entries_when_true():
    df = _frame([(100, 100, 100, 100)] * 6)
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: True,
                      exit_decision=lambda w, p, h: "HOLD",
                      regime_ok={d: True for d in df.index})
    assert out["positions_count"].max() == 1


def test_build_regime_map_tracks_index_vs_ema():
    n = 30
    idx = pd.bdate_range("2026-01-01", periods=n)
    rising = pd.Series(np.linspace(100.0, 130.0, n), index=idx)
    bench = pd.DataFrame({"open": rising, "high": rising, "low": rising,
                          "close": rising, "volume": np.full(n, 1e6)}, index=idx)
    assert build_regime_map(bench, ema_period=5)[idx[-1]] is True

    falling = pd.Series(np.linspace(130.0, 100.0, n), index=idx)
    bench_down = bench.assign(close=falling)
    assert build_regime_map(bench_down, ema_period=5)[idx[-1]] is False


# ──────────────────────────────────────────────
# H2: trailing exits
# ──────────────────────────────────────────────

_H2_ROWS = [
    (100, 100, 100, 100),   # d0
    (100, 100, 100, 100),   # d1: signal close
    (100, 101, 99, 100),    # d2: entry @ open 100 (stop 98.5)
    (105, 106, 104, 105),   # d3: +5% -> trail activates, stop -> 101.85
    (110, 111, 109, 110),   # d4: stop -> 106.70
    (115, 116, 114, 115),   # d5: stop -> 111.55
    (120, 121, 119, 120),   # d6: stop -> 116.40
    (118, 118, 110, 111),   # d7: low 110 breaches 116.40 -> stop fill
    (111, 111, 111, 111),   # d8
]


def test_trailing_exit_lets_winner_run_past_8pct():
    df = _frame(_H2_ROWS)
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=lambda w, p, h: "HOLD",
                      trailing_exit=True)
    log = out["trade_log"]
    assert len(log) == 1
    row = log.iloc[0]
    assert row["exit_reason"] == "STOP_LOSS"          # the *trailed* stop
    assert row["exit_price"] == 116.4                 # 120 * 0.97
    assert row["net_pnl_pct"] > 8.0                   # ran past the old fixed target


def test_fixed_target_still_caps_when_trailing_off():
    df = _frame(_H2_ROWS)
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=lambda w, p, h: "HOLD",
                      trailing_exit=False)
    row = out["trade_log"].iloc[0]
    assert row["exit_reason"] == "TARGET_HIT"
    assert row["exit_price"] == 110.0                 # d4 gaps above the 108 target


# ──────────────────────────────────────────────
# H3: relative-strength entries
# ──────────────────────────────────────────────

def _rs_frames(stock_slope: float, bench_slope: float, n: int = 80):
    idx = pd.bdate_range("2026-01-01", periods=n)
    s = 100 + np.arange(n) * stock_slope
    b = 100 + np.arange(n) * bench_slope
    stock = pd.DataFrame({"open": s, "high": s + 1, "low": s - 1, "close": s,
                          "volume": np.full(n, 500000.0)}, index=idx)
    bench = pd.DataFrame({"open": b, "high": b + 1, "low": b - 1, "close": b,
                          "volume": np.full(n, 1e6)}, index=idx)
    return stock, bench


def test_rs_filter_rejects_underperformer(monkeypatch):
    monkeypatch.setattr(config, "RS_FILTER_ENABLED", True)
    stock, bench = _rs_frames(stock_slope=0.05, bench_slope=0.5)
    result = check_entry_signal(stock, nifty_df=bench, strategy_mode="RELAXED")
    assert result["signal"] is False
    assert "[FAIL] RS" in result["reason"]


def test_rs_filter_marks_outperformer_pass(monkeypatch):
    monkeypatch.setattr(config, "RS_FILTER_ENABLED", True)
    stock, bench = _rs_frames(stock_slope=0.5, bench_slope=0.05)
    result = check_entry_signal(stock, nifty_df=bench, strategy_mode="RELAXED")
    assert "[PASS] RS" in result["reason"]


def test_rs_condition_absent_when_disabled():
    stock, bench = _rs_frames(stock_slope=0.5, bench_slope=0.05)
    result = check_entry_signal(stock, nifty_df=bench, strategy_mode="RELAXED")
    assert "vs Nifty" not in result["reason"]


# ──────────────────────────────────────────────
# H2 interplay: partial exit must not lower a trailed stop
# ──────────────────────────────────────────────

def test_partial_breakeven_is_a_floor_not_a_reset():
    d = pd.Timestamp("2026-01-02")
    positions = {"AAA": {"symbol": "AAA", "entry_date": d, "entry_price": 100.0,
                         "qty": 10, "stop_loss": 106.7,   # already trailed above entry
                         "target": float("inf"), "partial_taken": False,
                         "entry_cost": 0.8}}
    trades = []
    pe._book_partial(positions, trades, "AAA", 110.0, d, side_cost=0.0008)
    assert positions["AAA"]["stop_loss"] == 106.7   # NOT reset down to 100


# ──────────────────────────────────────────────
# H1 in the paper engine: is_market_regime_ok
# ──────────────────────────────────────────────

def test_paper_regime_helper_tracks_index_vs_ema():
    from paper_trade.paper_engine import is_market_regime_ok
    n = 30
    idx = pd.bdate_range("2026-01-01", periods=n)
    rising = pd.Series(np.linspace(100.0, 130.0, n), index=idx)
    bench = pd.DataFrame({"open": rising, "high": rising, "low": rising,
                          "close": rising, "volume": np.full(n, 1e6)}, index=idx)
    assert is_market_regime_ok(bench, ema_period=5) is True
    falling = bench.assign(close=pd.Series(np.linspace(130.0, 100.0, n), index=idx))
    assert is_market_regime_ok(falling, ema_period=5) is False


def test_paper_regime_helper_fails_open_without_data():
    from paper_trade.paper_engine import is_market_regime_ok
    assert is_market_regime_ok(None) is True                      # no benchmark
    idx = pd.bdate_range("2026-01-01", periods=3)
    short = pd.DataFrame({"open": [1, 1, 1], "high": [1, 1, 1], "low": [1, 1, 1],
                          "close": [1, 1, 1], "volume": [1, 1, 1]}, index=idx)
    assert is_market_regime_ok(short, ema_period=200) is True     # EMA still NaN


# ──────────────────────────────────────────────
# Regression: tiny windows must not crash the screener
# ──────────────────────────────────────────────

def test_check_entry_signal_degrades_on_tiny_window():
    # Walk-forward segments run with warmup=0, so the first days hand the
    # screener 1-4 row windows. It must say "no signal", not raise IndexError.
    stock, _ = _rs_frames(stock_slope=0.5, bench_slope=0.05)
    for n in (1, 2, 3, 4):
        result = check_entry_signal(stock.iloc[:n], strategy_mode="RELAXED")
        assert result["signal"] is False
        assert "need >= 5" in result["reason"]
