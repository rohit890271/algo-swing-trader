"""Shared pytest fixtures.

Builds deterministic synthetic OHLCV data so the strategy's pure functions
can be tested without any network calls to Yahoo Finance.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

# Make the project root importable when pytest is run from anywhere.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _make_ohlcv(n: int, start: float = 100.0, step: float = 1.0,
                seed: int = 0) -> pd.DataFrame:
    """Return an ``n``-bar synthetic OHLCV frame with a business-day index.

    A gently rising close with small intrabar ranges — enough structure for
    TA-Lib indicators to warm up and produce finite values.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-06-01", periods=n)
    close = start + np.arange(n) * step + rng.normal(0, 0.2, n)
    close = np.maximum(close, 1.0)
    high = close + np.abs(rng.normal(0.5, 0.2, n))
    low = close - np.abs(rng.normal(0.5, 0.2, n))
    open_ = close - rng.normal(0, 0.3, n)
    volume = rng.integers(400_000, 800_000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


@pytest.fixture
def ohlcv_250() -> pd.DataFrame:
    """250 bars — long enough for EMA-200 to warm up."""
    return _make_ohlcv(250)


@pytest.fixture
def ohlcv_60() -> pd.DataFrame:
    """60 bars — enough for RSI(14) and exit checks."""
    return _make_ohlcv(60)
