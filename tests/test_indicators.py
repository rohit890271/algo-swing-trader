"""Smoke tests for indicator enrichment."""

from __future__ import annotations

import numpy as np

from strategy.indicators import enrich_with_indicators

EXPECTED_COLS = [
    "ema_20", "ema_50", "ema_200", "rsi", "adx", "atr",
    "high_10d", "high_20d", "return_1w_pct", "vol_avg_5d",
]


def test_enrich_adds_all_columns(ohlcv_250):
    out = enrich_with_indicators(ohlcv_250)
    for col in EXPECTED_COLS:
        assert col in out.columns, f"missing {col}"


def test_enrich_does_not_mutate_input(ohlcv_250):
    cols_before = list(ohlcv_250.columns)
    enrich_with_indicators(ohlcv_250)
    assert list(ohlcv_250.columns) == cols_before  # copy(), not in-place


def test_indicators_finite_on_latest_bar(ohlcv_250):
    latest = enrich_with_indicators(ohlcv_250).iloc[-1]
    for col in ["ema_20", "ema_50", "ema_200", "rsi", "adx", "atr"]:
        assert np.isfinite(latest[col]), f"{col} is not finite"


def test_rsi_in_valid_range(ohlcv_250):
    rsi = enrich_with_indicators(ohlcv_250)["rsi"].dropna()
    assert ((rsi >= 0) & (rsi <= 100)).all()
