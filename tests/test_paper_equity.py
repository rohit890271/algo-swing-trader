"""Tests for forward paper-test state persistence.

Trade accounting itself is shared with ``backtest.portfolio_engine`` (see
``test_portfolio_engine_partial.py``); these cover the paper engine's own
persistence layer.  Fill/cost/mark-to-market parity lives in
``test_paper_forward.py``.
"""
from __future__ import annotations

from paper_trade import paper_engine as pp


def test_state_round_trips_to_disk(tmp_path):
    path = tmp_path / "portfolio_state.json"
    pp.save_portfolio_state({"equity": 101000.0, "cash": 95000.0,
                             "realized_pnl": 1000.0}, str(path))
    loaded = pp.load_portfolio_state(str(path))
    assert loaded["equity"] == 101000.0
    assert loaded["cash"] == 95000.0
    assert loaded["realized_pnl"] == 1000.0


def test_load_defaults_when_missing(tmp_path):
    loaded = pp.load_portfolio_state(str(tmp_path / "missing.json"))
    assert loaded["equity"] == pp.INITIAL_CAPITAL
    assert loaded["realized_pnl"] == 0.0


def test_corrupt_state_falls_back_to_starting_capital(tmp_path):
    # A truncated write must not wedge the forward test on the next run.
    path = tmp_path / "corrupt.json"
    path.write_text("{not json")
    assert pp.load_portfolio_state(str(path))["equity"] == pp.INITIAL_CAPITAL


def test_open_positions_round_trip(tmp_path, monkeypatch):
    path = str(tmp_path / "open_positions.json")
    monkeypatch.setattr(pp, "OPEN_POSITIONS_FILE", path)
    book = {"AAA": {"entry_price": 100.0, "qty": 10, "stop_loss": 95.0,
                    "target": 108.0, "partial_taken": False, "entry_cost": 8.0,
                    "entry_date": "2026-07-20"}}
    pp.save_open_positions(book)
    assert pp.load_open_positions() == book
