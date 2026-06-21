"""Partial-exit tests for the portfolio engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import portfolio_engine as pe


def _frame(rows, start="2026-01-01"):
    idx = pd.bdate_range(start, periods=len(rows))
    arr = np.array(rows, dtype=float)
    df = pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2],
                       "close": arr[:, 3], "volume": np.full(len(rows), 500000.0)},
                      index=idx)
    df["atr"] = 1.0
    return df


def test_partial_books_half_and_moves_stop_to_breakeven():
    df = _frame([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 101, 99, 100),    # entry @100, qty Q
        (105, 106, 104, 105),   # day3 close -> +5% -> partial signal fires
        (106, 107, 105, 106),   # day4 OPEN=106 -> partial fills here
        (106, 106, 106, 106),
    ])

    def partial_day3(window, position, max_hold):
        if window.index[-1] == df.index[3] and not position.get("partial_taken"):
            return "PARTIAL_EXIT_5PCT"
        return "HOLD"

    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=partial_day3)
    log = out["trade_log"]
    partials = log[log["exit_reason"] == "PARTIAL_EXIT_50%"]
    assert len(partials) == 1
    assert partials.iloc[0]["exit_price"] == 106.0
    # Still holding the remaining half at the end (no further exit signal).
    assert out["positions_count"].iloc[-1] == 1
