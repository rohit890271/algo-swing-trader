"""Forward paper-test parity tests.

The forward test only answers "is the edge real?" if it books trades the same
way the backtest does: next-open fills, costs on both legs, sizing off running
equity, and a mark-to-market equity curve.  These pin that parity.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from paper_trade import paper_engine as pp


def _bar(date, o, h, l, c, v=500000.0):
    return pd.DataFrame(
        {"open": [o], "high": [h], "low": [l], "close": [c], "volume": [v]},
        index=pd.DatetimeIndex([pd.Timestamp(date)]),
    )


# ──────────────────────────────────────────────
# Mark-to-market equity
# ──────────────────────────────────────────────

def test_mark_to_market_adds_open_position_value():
    positions = {"AAA": {"qty": 10}, "BBB": {"qty": 5}}
    prices = {"AAA": 100.0, "BBB": 200.0}
    assert pp.mark_to_market(50000.0, positions, prices) == 50000.0 + 1000.0 + 1000.0


def test_mark_to_market_is_cash_when_flat():
    assert pp.mark_to_market(100000.0, {}, {}) == 100000.0


def test_mark_to_market_skips_unpriced_symbols():
    # A symbol whose data failed to download must not crash the run; it is
    # carried at zero rather than guessed at.
    positions = {"AAA": {"qty": 10}, "STALE": {"qty": 5}}
    assert pp.mark_to_market(1000.0, positions, {"AAA": 100.0}) == 2000.0


# ──────────────────────────────────────────────
# Costs: parity with the backtest cost model
# ──────────────────────────────────────────────

def test_entry_cost_is_one_side_of_notional():
    # 100 shares @ 100 => 10,000 notional; one side is 0.08% (0.03 + 0.05)
    assert pp.entry_cost(100.0, 100) == pytest.approx(10000.0 * 0.0008)


def test_round_trip_costs_match_backtest_model():
    from backtest.costs import trade_cost
    entry, exit_px, qty = 100.0, 110.0, 50
    paper = pp.entry_cost(entry, qty) + pp.entry_cost(exit_px, qty)
    assert paper == pytest.approx(trade_cost(entry, exit_px, qty), abs=1e-6)


# ──────────────────────────────────────────────
# Sizing off running equity, not the static constant
# ──────────────────────────────────────────────

def test_sizing_uses_running_equity_not_initial_capital():
    # Doubling equity must roughly double the share count for the same setup.
    small = pp.size_for_equity(100000.0, entry_price=100.0, stop_loss=95.0)
    big = pp.size_for_equity(200000.0, entry_price=100.0, stop_loss=95.0)
    assert big == pytest.approx(small * 2, rel=0.02)


def test_sizing_returns_zero_when_stop_is_not_below_entry():
    # Degenerate risk must not raise or produce a fabricated fallback quantity.
    assert pp.size_for_equity(100000.0, entry_price=100.0, stop_loss=100.0) == 0


# ──────────────────────────────────────────────
# Next-open fills: a signal never fills on its own bar
# ──────────────────────────────────────────────

def test_pending_fills_only_after_a_newer_bar_arrives():
    assert pp.should_fill_pending(signal_date="2026-07-20", bar_date="2026-07-21")
    # Same bar => the open we would fill at has not printed yet.
    assert not pp.should_fill_pending(signal_date="2026-07-21", bar_date="2026-07-21")
    # A stale/older bar (bad download) must never trigger a fill.
    assert not pp.should_fill_pending(signal_date="2026-07-21", bar_date="2026-07-20")


def test_pending_state_round_trips(tmp_path):
    path = tmp_path / "pending.json"
    payload = {"entries": {"AAA": {"signal_date": "2026-07-20"}},
               "exits": {"BBB": {"signal_date": "2026-07-20", "reason": "TIME_EXIT"}}}
    pp.save_pending(payload, str(path))
    assert pp.load_pending(str(path)) == payload


def test_pending_defaults_to_empty_queues(tmp_path):
    assert pp.load_pending(str(tmp_path / "none.json")) == {"entries": {}, "exits": {}}


# ──────────────────────────────────────────────
# Portfolio state carries cash as well as equity
# ──────────────────────────────────────────────

def test_state_defaults_cash_to_initial_capital(tmp_path):
    state = pp.load_portfolio_state(str(tmp_path / "missing.json"))
    assert state["cash"] == pp.INITIAL_CAPITAL
    assert state["equity"] == pp.INITIAL_CAPITAL


def test_legacy_state_without_cash_backfills_from_equity(tmp_path):
    # States written before mark-to-market existed only carried equity.
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"equity": 105000.0, "realized_pnl": 5000.0}))
    state = pp.load_portfolio_state(str(path))
    assert state["cash"] == 105000.0


def test_state_round_trips_cash(tmp_path):
    path = tmp_path / "state.json"
    pp.save_portfolio_state({"equity": 101000.0, "cash": 90000.0,
                             "realized_pnl": 1000.0}, str(path))
    assert pp.load_portfolio_state(str(path))["cash"] == 90000.0


# ──────────────────────────────────────────────
# Equity curve accumulates one row per bar date
# ──────────────────────────────────────────────

def test_equity_curve_appends_new_dates(tmp_path):
    path = str(tmp_path / "equity.csv")
    pp.append_equity_point(path, "2026-07-20", 100000.0)
    pp.append_equity_point(path, "2026-07-21", 101000.0)
    curve = pp.load_equity_curve(path)
    assert list(curve.values) == [100000.0, 101000.0]


def test_equity_curve_rewrites_same_date_instead_of_duplicating(tmp_path):
    # Running the engine twice in one day must not create two points for that
    # bar -- that would corrupt the daily-return series feeding Sharpe.
    path = str(tmp_path / "equity.csv")
    pp.append_equity_point(path, "2026-07-20", 100000.0)
    pp.append_equity_point(path, "2026-07-20", 100500.0)
    curve = pp.load_equity_curve(path)
    assert len(curve) == 1
    assert curve.iloc[0] == 100500.0


def test_empty_equity_curve_loads_as_empty_series(tmp_path):
    curve = pp.load_equity_curve(str(tmp_path / "nothing.csv"))
    assert len(curve) == 0
