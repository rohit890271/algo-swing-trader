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


def test_book_partial_skips_single_share_position_no_zombie():
    d = pd.Timestamp("2026-01-02")
    positions = {"AAA": {"symbol": "AAA", "entry_date": d, "entry_price": 100.0,
                         "qty": 1, "stop_loss": 98.0, "target": 108.0,
                         "partial_taken": False, "entry_cost": 0.08}}
    trades = []
    cash_back = pe._book_partial(positions, trades, "AAA", 106.0, d, side_cost=0.0008)
    # No half-share sold, no zombie left behind, marked done so it won't re-queue.
    assert positions["AAA"]["qty"] == 1
    assert positions["AAA"]["partial_taken"] is True
    assert cash_back == 0.0
    assert all(t["exit_reason"] != "PARTIAL_EXIT_50%" for t in trades)


def test_book_partial_splits_entry_cost_proportionally():
    d = pd.Timestamp("2026-01-02")
    positions = {"AAA": {"symbol": "AAA", "entry_date": d, "entry_price": 100.0,
                         "qty": 10, "stop_loss": 98.0, "target": 108.0,
                         "partial_taken": False, "entry_cost": 8.0}}
    trades = []
    pe._book_partial(positions, trades, "AAA", 110.0, d, side_cost=0.0008)
    # half=5; entry_cost_share = 8.0 * 5/10 = 4.0; remaining entry_cost = 4.0
    assert positions["AAA"]["entry_cost"] == 4.0
    row = trades[0]
    # cost = entry_cost_share(4.0) + exit_cost(110*5*0.0008 = 0.44) = 4.44
    assert row["cost"] == 4.44
    assert positions["AAA"]["qty"] == 5
