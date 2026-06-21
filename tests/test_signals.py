"""Smoke tests for the entry/exit screeners."""

from __future__ import annotations

import pytest

from strategy.indicators import enrich_with_indicators
from strategy.signals import check_entry_signal, check_exit_signal


# ── Entry screener contract ───────────────────

def test_check_entry_signal_returns_contract(ohlcv_250):
    df = enrich_with_indicators(ohlcv_250)
    result = check_entry_signal(df, strategy_mode="RELAXED")
    assert set(result.keys()) == {"signal", "reason"}
    assert isinstance(result["signal"], bool)
    assert "RELAXED MODE" in result["reason"]


def test_check_entry_signal_computes_indicators_if_missing(ohlcv_250):
    # Pass raw OHLCV (no indicator columns) — function should enrich internally.
    result = check_entry_signal(ohlcv_250, strategy_mode="STRICT")
    assert isinstance(result["signal"], bool)
    assert "STRICT MODE" in result["reason"]


# ── Exit priority ordering ────────────────────

def _enriched(ohlcv):
    return enrich_with_indicators(ohlcv)


def test_exit_target_hit_takes_priority(ohlcv_60):
    df = _enriched(ohlcv_60)
    last = df["close"].iloc[-1]
    reason = check_exit_signal(df, entry_price=last - 10, entry_date=df.index[-2],
                               stop_loss=last - 20, target=last - 1, max_hold_days=7)
    assert reason == "TARGET_HIT"


def test_exit_stop_loss(ohlcv_60):
    df = _enriched(ohlcv_60)
    last = df["close"].iloc[-1]
    reason = check_exit_signal(df, entry_price=last + 10, entry_date=df.index[-2],
                               stop_loss=last + 1, target=last + 100, max_hold_days=7)
    assert reason == "STOP_LOSS"


def test_exit_partial_at_5pct(ohlcv_60):
    df = _enriched(ohlcv_60)
    last = df["close"].iloc[-1]
    entry = last / 1.06  # ~+6% gain, above the 5% partial threshold
    reason = check_exit_signal(df, entry_price=entry, entry_date=df.index[-2],
                               stop_loss=entry * 0.9, target=entry * 2,
                               max_hold_days=7, partial_taken=False)
    assert reason == "PARTIAL_EXIT_5PCT"


def test_exit_hold_when_nothing_triggers(ohlcv_60):
    df = _enriched(ohlcv_60)
    last = df["close"].iloc[-1]
    # Flat trade, partial already taken, wide stop/target, fresh entry -> HOLD.
    reason = check_exit_signal(df, entry_price=last, entry_date=df.index[-2],
                               stop_loss=last * 0.8, target=last * 1.5,
                               max_hold_days=7, partial_taken=True)
    assert reason in {"HOLD", "MOMENTUM_FADE"}  # depends only on synthetic RSI


def test_exit_requires_two_rows():
    import pandas as pd
    df = pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1],
                       "volume": [1]}, index=pd.bdate_range("2026-01-01", periods=1))
    with pytest.raises(ValueError):
        check_exit_signal(df, entry_price=1, entry_date=df.index[-1],
                          stop_loss=0.5, target=2)
