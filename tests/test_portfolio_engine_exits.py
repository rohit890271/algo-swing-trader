"""Exit-path tests for the portfolio engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import portfolio_engine as pe


def _frame(rows, start="2026-01-01"):
    """rows: list of (open, high, low, close). Volume fixed, atr=1.0 attached."""
    idx = pd.bdate_range(start, periods=len(rows))
    arr = np.array(rows, dtype=float)
    df = pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2],
                       "close": arr[:, 3], "volume": np.full(len(rows), 500000.0)},
                      index=idx)
    df["atr"] = 1.0
    return df


def test_target_hit_closes_position_with_costs():
    # Enter day2 open=100. calculate_target(100,0.08)=108. Day3 high=109 -> target fill 108.
    df = _frame([
        (100, 100, 100, 100),   # day0
        (100, 100, 100, 100),   # day1 (signal close)
        (100, 101, 99, 100),    # day2 entry @ open 100
        (100, 109, 100, 108),   # day3 target hit
        (108, 108, 108, 108),   # day4
    ])

    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=lambda w, p, h: "HOLD")
    log = out["trade_log"]
    assert len(log) == 1
    row = log.iloc[0]
    assert row["exit_reason"] == "TARGET_HIT"
    assert row["entry_price"] == 100.0
    assert row["exit_price"] == 108.0
    # gross = qty*(108-100); cost > 0; net = gross - cost; net_pnl < gross_pnl
    assert row["net_pnl"] < row["gross_pnl"]
    assert row["cost"] > 0


def test_stop_checked_before_target_when_both_touched():
    # calculate_atr_stop_loss(100, atr=1.0, mult 1.5)=98.5 (raw 1.5%). target=108.
    # Day3 both: low=98 (<=98.5 stop) and high=109 (>=108 target). Stop must win.
    df = _frame([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 101, 99, 100),    # entry @100
        (100, 109, 98, 99),     # both stop and target touched
        (99, 99, 99, 99),
    ])
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=lambda w, p, h: "HOLD")
    row = out["trade_log"].iloc[0]
    assert row["exit_reason"] == "STOP_LOSS"
    assert row["exit_price"] == 98.5    # stop level, no gap (open 100 > stop)


def test_discretionary_exit_fills_next_open():
    df = _frame([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 101, 99, 100),    # entry @100
        (101, 102, 100, 101),   # day3 close -> exit signal fires here
        (105, 106, 104, 105),   # day4 OPEN=105 -> discretionary fill here
    ])

    def exit_on_day3(window, position, max_hold):
        return "MOMENTUM_FADE" if window.index[-1] == df.index[3] else "HOLD"

    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=exit_on_day3)
    row = out["trade_log"].iloc[0]
    assert row["exit_reason"] == "MOMENTUM_FADE"
    assert row["exit_price"] == 105.0   # next-open, not the 101 signal close
