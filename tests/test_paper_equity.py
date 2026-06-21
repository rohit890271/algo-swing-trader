"""Tests for forward paper-test equity persistence."""
from __future__ import annotations

import json

from paper_trade import paper_engine as pp


def test_apply_realized_pnl_compounds():
    state = {"equity": 100000.0, "realized_pnl": 0.0}
    out = pp.apply_realized_pnl(state, pnl_amount=2500.0)
    assert out["equity"] == 102500.0
    assert out["realized_pnl"] == 2500.0


def test_state_round_trips_to_disk(tmp_path):
    path = tmp_path / "portfolio_state.json"
    pp.save_portfolio_state({"equity": 101000.0, "realized_pnl": 1000.0}, str(path))
    loaded = pp.load_portfolio_state(str(path))
    assert loaded["equity"] == 101000.0
    assert loaded["realized_pnl"] == 1000.0


def test_load_defaults_when_missing(tmp_path):
    path = tmp_path / "missing.json"
    loaded = pp.load_portfolio_state(str(path))
    assert loaded["equity"] == pp.INITIAL_CAPITAL
    assert loaded["realized_pnl"] == 0.0
