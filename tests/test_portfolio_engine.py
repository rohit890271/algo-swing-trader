"""Tests for the pure portfolio simulation engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import portfolio_engine as pe


def _flat_frame(prices, start="2026-01-01"):
    """OHLCV frame where open==high==low==close==price each day, fixed volume."""
    idx = pd.bdate_range(start, periods=len(prices))
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"open": p, "high": p, "low": p, "close": p,
                         "volume": np.full(len(p), 500000.0)}, index=idx)


def _enrich_stub(df):
    """Attach the indicator columns the position-sizing path reads, with safe values."""
    df = df.copy()
    df["atr"] = 1.0
    return df


def test_entry_fills_at_next_open_not_signal_close():
    # Price rises each day. Signal fires on day index 1 (close), fill must be day 2 open.
    df = _enrich_stub(_flat_frame([100, 101, 102, 103, 104]))
    data = {"AAA": df}

    def entry_on_day1(window, mode):
        return window.index[-1] == df.index[1]   # only signal at the 2nd bar's close

    def never_exit(window, position, max_hold):
        return "HOLD"

    out = pe.simulate(data, start_capital=100000, max_positions=4,
                      warmup=0, entry_decision=entry_on_day1, exit_decision=never_exit)
    # No completed trades (position still open at end), but one position was opened.
    # Verify via equity: cash dropped by qty*open_price(day2)=102*qty at fill.
    assert out["positions_count"].iloc[-1] == 1
    # The fill price recorded is day-2 open (102), proving next-open (not 101 signal close).
    assert out["_debug_last_entry_price"] == 102.0


def test_capacity_cap_respected():
    data = {}
    for i, sym in enumerate(["A", "B", "C", "D", "E"]):
        data[sym] = _enrich_stub(_flat_frame([100, 100, 100, 100, 100]))

    def always_enter(window, mode):
        return True

    def never_exit(window, position, max_hold):
        return "HOLD"

    out = pe.simulate(data, start_capital=100000, max_positions=3,
                      warmup=0, entry_decision=always_enter, exit_decision=never_exit)
    assert out["positions_count"].max() <= 3


def test_no_entry_when_signal_never_fires():
    df = _enrich_stub(_flat_frame([100, 101, 102]))
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: False,
                      exit_decision=lambda w, p, h: "HOLD")
    assert out["positions_count"].max() == 0
    assert out["trade_log"].empty
