"""Smoke tests for the pure risk-management functions."""

from __future__ import annotations

import pytest

from strategy import risk


# ── Position sizing ───────────────────────────

def test_position_size_basic():
    # Risk 1% of 100k = 1000; risk/share = 10 -> 100 shares.
    qty = risk.position_size(capital=100_000, entry_price=100, stop_loss_price=90,
                             risk_pct=0.01)
    assert qty == 100


def test_position_size_floors_to_int():
    qty = risk.position_size(capital=100_000, entry_price=100, stop_loss_price=93,
                             risk_pct=0.0075)
    # 750 / 7 = 107.14 -> floored to 107
    assert qty == 107
    assert isinstance(qty, int)


@pytest.mark.parametrize("kwargs", [
    {"capital": 0, "entry_price": 100, "stop_loss_price": 90},
    {"capital": 100_000, "entry_price": -1, "stop_loss_price": 90},
    {"capital": 100_000, "entry_price": 100, "stop_loss_price": 100},   # equal
    {"capital": 100_000, "entry_price": 100, "stop_loss_price": 90, "risk_pct": 1.5},
])
def test_position_size_validation(kwargs):
    with pytest.raises(ValueError):
        risk.position_size(**kwargs)


# ── ATR stop loss (clamped) ───────────────────

def test_atr_stop_within_band():
    # 1.5 x 25 = 37.5 -> 3.75% of 1000, inside the 1.5%-4% band.
    assert risk.calculate_atr_stop_loss(1000.0, atr_value=25.0) == 962.5


def test_atr_stop_floor():
    # Tiny ATR -> raw 0.75%, clamped up to the 1.5% floor.
    assert risk.calculate_atr_stop_loss(1000.0, atr_value=5.0) == 985.0


def test_atr_stop_ceiling():
    # Huge ATR -> raw 7.5%, clamped down to the 4% ceiling.
    assert risk.calculate_atr_stop_loss(1000.0, atr_value=50.0) == 960.0


def test_atr_stop_validation():
    with pytest.raises(ValueError):
        risk.calculate_atr_stop_loss(1000.0, atr_value=0.0)


# ── Target / R:R ──────────────────────────────

def test_calculate_target():
    assert risk.calculate_target(1000.0, target_pct=0.08) == 1080.0


def test_take_profit_rr():
    # entry 100, stop 90 -> risk 10; 2:1 -> target 120.
    assert risk.take_profit_price(100, 90, rr_ratio=2.0) == 120


# ── Portfolio constraints ─────────────────────

def test_can_open_new_position_blocks_on_total():
    assert risk.can_open_new_position(total_open_positions=4, sector_open_positions=0) is False


def test_can_open_new_position_blocks_on_sector():
    assert risk.can_open_new_position(total_open_positions=1, sector_open_positions=2) is False


def test_can_open_new_position_allows():
    assert risk.can_open_new_position(total_open_positions=1, sector_open_positions=1) is True


# ── Trailing stop activation ──────────────────

def test_trailing_stop_inactive_below_threshold():
    out = risk.trailing_stop(entry_price=100, current_price=103)  # +3%, < 4% trigger
    assert out["active"] is False
    assert out["stop_price"] is None


def test_trailing_stop_active_above_threshold():
    out = risk.trailing_stop(entry_price=100, current_price=110, trail_pct=0.03)
    assert out["active"] is True
    assert out["stop_price"] == pytest.approx(106.7, abs=0.01)
