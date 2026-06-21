"""Tests for the thin backtest runner (no network)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import run_portfolio


def _frame(n, start="2025-01-01"):
    idx = pd.bdate_range(start, periods=n)
    p = 100 + np.arange(n) * 0.1
    return pd.DataFrame({"open": p, "high": p + 0.5, "low": p - 0.5,
                         "close": p, "volume": np.full(n, 500000.0)}, index=idx)


def test_runner_returns_metrics_via_injected_loader():
    # Injected loader returns deterministic frames; no Yahoo calls.
    def fake_loader(symbol, days):
        return _frame(300)

    result = run_portfolio.run(watchlist=["AAA", "BBB"], days=300, loader=fake_loader,
                               entry_decision=lambda w, m: False)  # no trades -> safe
    assert "metrics" in result
    assert "metrics_haircut" in result
    assert result["metrics"]["total_trades"] == 0
    # haircut copy exists and is <= base on return fields
    assert result["metrics_haircut"]["total_return_pct"] <= result["metrics"]["total_return_pct"]


def test_runner_skips_symbols_with_insufficient_history():
    def short_loader(symbol, days):
        return _frame(10)   # far fewer than the 250-bar minimum

    result = run_portfolio.run(watchlist=["AAA"], days=300, loader=short_loader,
                               entry_decision=lambda w, m: False)
    assert result["metrics"]["total_trades"] == 0
