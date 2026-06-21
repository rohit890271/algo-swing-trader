"""Regression test: walk-forward segments must not be starved by the engine warm-up."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.indicators import enrich_with_indicators
from backtest import walk_forward as wf


def _enriched(n):
    idx = pd.bdate_range("2024-01-01", periods=n)
    p = 100 + np.arange(n) * 0.1
    df = pd.DataFrame({"open": p, "high": p + 0.5, "low": p - 0.5, "close": p,
                       "volume": np.full(n, 500000.0)}, index=idx)
    return enrich_with_indicators(df)


def test_segment_pf_not_starved_by_default_warmup():
    # A 70-row slice of already-warmed (post-200) enriched data must be able to trade.
    full = _enriched(320)
    sl = full.iloc[250:320]
    data = {"AAA": sl}

    def entry_stub(window, mode):
        return window.index[-1] == sl.index[1]      # enter on the 2nd bar of the slice

    def exit_stub(window, position, max_hold):
        return "MOMENTUM_FADE" if window.index[-1] == sl.index[5] else "HOLD"

    pf = wf._segment_pf(data, entry_decision=entry_stub, exit_decision=exit_stub)
    # With the old warmup=200 default the 70-row slice yields zero trades -> PF 0.0.
    assert pf != 0.0
