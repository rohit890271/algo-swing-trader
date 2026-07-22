"""End-to-end tests for the paper engine's daily job.

Drives ``run_daily_job`` across successive synthetic sessions with the network
stubbed out, verifying the fill model actually behaves like the backtest:
a signal on bar D fills at bar D+1's *open*, never on its own bar.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import config
from paper_trade import paper_engine as pp


@pytest.fixture
def paper_env(tmp_path, monkeypatch):
    """Redirect every persisted artifact into a temp dir and stub the network."""
    for name, fname in [
        ("OPEN_POSITIONS_FILE", "open_positions.json"),
        ("CLOSED_TRADES_FILE", "closed_trades.csv"),
        ("PORTFOLIO_STATE_FILE", "portfolio_state.json"),
        ("PENDING_FILE", "pending_orders.json"),
        ("EQUITY_CURVE_FILE", "equity_curve.csv"),
        ("DAILY_SCAN_LOG_FILE", "daily_scan_log.csv"),
    ]:
        monkeypatch.setattr(pp, name, str(tmp_path / fname))
    # Benchmark absent -> regime filter fails open, so entries are not gated.
    monkeypatch.setattr(pp, "fetch_nifty_benchmark", lambda days=500: None)
    monkeypatch.setattr(pp, "WATCHLIST", ["AAA"])
    return tmp_path


BASE_BARS = 60      # enough history for the engine's 50-bar minimum


def _series(closes, opens=None, highs=None, lows=None, start="2026-01-01"):
    n = len(closes)
    idx = pd.bdate_range(start, periods=n)
    c = np.array(closes, dtype=float)
    o = np.array(opens, dtype=float) if opens is not None else c
    h = np.array(highs, dtype=float) if highs is not None else np.maximum(o, c)
    l = np.array(lows, dtype=float) if lows is not None else np.minimum(o, c)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": np.full(n, 5_000_000.0)}, index=idx)


def _sessions(extra_bars):
    """Build one continuous history, then slice it into successive sessions.

    Appending separately-dated frames risks colliding on the same bdate, which
    would silently suppress fills; slicing one series cannot.  ``extra_bars`` is
    a list of ``(open, high, low, close)`` appended after a flat 100.0 base.
    """
    closes = [100.0] * BASE_BARS + [b[3] for b in extra_bars]
    opens = [100.0] * BASE_BARS + [b[0] for b in extra_bars]
    highs = [100.0] * BASE_BARS + [b[1] for b in extra_bars]
    lows = [100.0] * BASE_BARS + [b[2] for b in extra_bars]
    full = _series(closes, opens, highs, lows)
    return {i: full.iloc[: BASE_BARS + i] for i in range(len(extra_bars) + 1)}


def _install_data(monkeypatch, df_by_day):
    """Serve a different history slice on each successive call to the loader."""
    state = {"i": 0}

    def loader(symbol, days=365):
        return df_by_day[state["i"]]

    monkeypatch.setattr(pp, "get_ohlcv_free", loader)
    return state


def test_entry_signal_fills_at_next_bar_open(paper_env, monkeypatch):
    # Force a signal every scan; the engine must still defer the fill one bar.
    monkeypatch.setattr(pp, "check_entry_signal",
                        lambda df, **kw: {"signal": True, "reason": "[PASS] forced"})
    monkeypatch.setattr(pp, "check_exit_signal", lambda **kw: "HOLD")

    # Session 1 adds a bar that OPENS at 110 -- the price the fill must use.
    state = _install_data(monkeypatch, _sessions([(110.0, 113.0, 109.0, 112.0)]))

    pp.run_daily_job()
    pending = json.loads(open(paper_env / "pending_orders.json").read())
    assert "AAA" in pending["entries"], "signal must queue, not fill, on its own bar"
    assert json.loads(open(paper_env / "open_positions.json").read()) == {}

    state["i"] = 1
    pp.run_daily_job()
    positions = json.loads(open(paper_env / "open_positions.json").read())
    assert "AAA" in positions
    # Filled at the OPEN (110), never at the signal bar's close (100) or the
    # fill bar's close (112).
    assert positions["AAA"]["entry_price"] == pytest.approx(110.0)


def test_entry_charges_one_side_cost_and_debits_cash(paper_env, monkeypatch):
    monkeypatch.setattr(pp, "check_entry_signal",
                        lambda df, **kw: {"signal": True, "reason": "[PASS] forced"})
    monkeypatch.setattr(pp, "check_exit_signal", lambda **kw: "HOLD")

    state = _install_data(monkeypatch, _sessions([(100.0, 101.0, 99.5, 100.0)]))

    pp.run_daily_job()
    state["i"] = 1
    pp.run_daily_job()

    pos = json.loads(open(paper_env / "open_positions.json").read())["AAA"]
    st = json.loads(open(paper_env / "portfolio_state.json").read())
    qty, px = pos["qty"], pos["entry_price"]
    assert pos["entry_cost"] == pytest.approx(pp.entry_cost(px, qty))
    # Cash must reflect notional AND the entry-leg cost.
    assert st["cash"] == pytest.approx(config.INITIAL_CAPITAL - qty * px - pos["entry_cost"])


def test_stop_loss_exit_books_a_net_loss_including_costs(paper_env, monkeypatch):
    monkeypatch.setattr(pp, "check_entry_signal",
                        lambda df, **kw: {"signal": True, "reason": "[PASS] forced"})
    monkeypatch.setattr(pp, "check_exit_signal", lambda **kw: "HOLD")

    # Session 2 collapses far below any ATR stop -> intrabar stop must fire.
    state = _install_data(monkeypatch, _sessions([
        (100.0, 101.0, 99.5, 100.0),
        (99.0, 99.0, 80.0, 80.0),
    ]))

    pp.run_daily_job()
    state["i"] = 1
    pp.run_daily_job()
    state["i"] = 2
    pp.run_daily_job()

    assert json.loads(open(paper_env / "open_positions.json").read()) == {}
    trades = pd.read_csv(paper_env / "closed_trades.csv")
    assert len(trades) == 1
    row = trades.iloc[0]
    assert row["exit_reason"] == "STOP_LOSS"
    assert row["net_pnl"] < 0
    # Costs are charged on both legs, so net is strictly worse than gross.
    assert row["net_pnl"] < row["gross_pnl"]
    assert row["cost"] > 0


def test_equity_curve_gets_one_point_per_session(paper_env, monkeypatch):
    monkeypatch.setattr(pp, "check_entry_signal",
                        lambda df, **kw: {"signal": False, "reason": "[FAIL] none"})
    monkeypatch.setattr(pp, "check_exit_signal", lambda **kw: "HOLD")

    state = _install_data(monkeypatch, _sessions([(101.0, 101.0, 101.0, 101.0)]))

    pp.run_daily_job()
    state["i"] = 1
    pp.run_daily_job()

    curve = pp.load_equity_curve(str(paper_env / "equity_curve.csv"))
    assert len(curve) == 2
    # Flat cash, no trades -> equity unchanged.
    assert curve.iloc[-1] == pytest.approx(config.INITIAL_CAPITAL)


def test_rerunning_same_bar_does_not_double_fill(paper_env, monkeypatch):
    monkeypatch.setattr(pp, "check_entry_signal",
                        lambda df, **kw: {"signal": True, "reason": "[PASS] forced"})
    monkeypatch.setattr(pp, "check_exit_signal", lambda **kw: "HOLD")

    state = _install_data(monkeypatch, _sessions([(100.0, 101.0, 99.5, 100.0)]))

    pp.run_daily_job()
    state["i"] = 1
    pp.run_daily_job()
    cash_after = json.loads(open(paper_env / "portfolio_state.json").read())["cash"]

    # A second run on the SAME bar must be a no-op for fills.
    pp.run_daily_job()
    assert json.loads(open(paper_env / "portfolio_state.json").read())["cash"] == cash_after
    curve = pp.load_equity_curve(str(paper_env / "equity_curve.csv"))
    assert len(curve) == 2      # not 3
