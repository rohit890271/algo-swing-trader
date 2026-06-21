# Phase 1 — Honest Backtest & Trusted Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-symbol, zero-cost, look-ahead-prone backtest with a portfolio-level, cost-aware, next-open-fill simulation that produces a single trusted baseline tear-sheet plus an out-of-sample walk-forward verdict.

**Architecture:** A **pure** simulation engine (`backtest/portfolio_engine.py`) takes pre-loaded, indicator-enriched price data and returns a trade log + equity curve + daily position count. It accepts injectable entry/exit decision functions (defaulting to the existing `check_entry_signal`/`check_exit_signal`) so its mechanics are testable with deterministic stubs. Costs live in `backtest/costs.py`; metrics/tear-sheet in `backtest/metrics.py`. A thin runner does all I/O (Yahoo fetch) and prints the tear-sheet. Walk-forward reuses the same engine over strict non-overlapping splits.

**Tech Stack:** Python 3.13, pandas, numpy, TA-Lib, pytest. Windows venv at `.venv/Scripts/python.exe`.

---

## Conventions for every task

- Run Python via the venv: `.venv/Scripts/python.exe`.
- Run a single test: `.venv/Scripts/python.exe -m pytest tests/<file>::<test> -v`
- Run the whole suite: `.venv/Scripts/python.exe -m pytest -q`
- OHLCV frames are lowercase `open/high/low/close/volume` with a `DatetimeIndex`.
- Commit messages end with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.
- Work happens on the existing `strategy-validation` branch.

## File structure (what each new/changed file is responsible for)

- `backtest/costs.py` *(new)* — pure trading-cost functions. No pandas state.
- `backtest/metrics.py` *(new)* — compute performance metrics from a trade log + equity curve; survivorship haircut; tear-sheet formatter.
- `backtest/portfolio_engine.py` *(new)* — the pure date-driven portfolio simulator.
- `backtest/run_portfolio.py` *(new)* — thin runner: load+enrich universe, call `simulate`, print tear-sheet, save trade log.
- `backtest/walk_forward.py` *(rewrite)* — strict non-overlapping train/test splits over the portfolio engine, with an out-of-sample pass/fail verdict.
- `paper_trade/paper_engine.py` *(modify)* — persist a running equity figure across daily runs for the forward paper-test.
- `config.py` *(modify)* — add `SURVIVORSHIP_HAIRCUT_PCT`.
- `main.py` *(modify)* — point at the portfolio runner.
- `tests/` *(new test files)* — one per new module.

---

## Task 1: Trading-cost model

**Files:**
- Create: `backtest/costs.py`
- Test: `tests/test_costs.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_costs.py
"""Tests for the pure trading-cost model."""
from __future__ import annotations

from backtest import costs


def test_one_side_cost_pct_matches_config():
    # COMMISSION_PCT=0.03 + SLIPPAGE_PCT=0.05 = 0.08% per side = 0.0008 fraction.
    assert costs.one_side_cost_pct() == 0.0008


def test_round_trip_is_two_sides():
    assert costs.round_trip_cost_pct() == 0.0016


def test_trade_cost_charges_both_legs():
    # 100 shares: entry 100 -> 10000 notional, exit 110 -> 11000 notional.
    # cost = (10000 + 11000) * 0.0008 = 16.8
    assert costs.trade_cost(entry_price=100.0, exit_price=110.0, qty=100) == 16.8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_costs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.costs'`

- [ ] **Step 3: Write minimal implementation**

```python
# backtest/costs.py
"""Pure trading-cost model.

Costs are expressed as a fraction of traded notional and charged on both
the entry and the exit leg of a round-trip trade.  Values come from
``config`` (``COMMISSION_PCT`` brokerage+charges, ``SLIPPAGE_PCT`` estimated
slippage), each a *percent* number (0.03 == 0.03%).
"""
from __future__ import annotations

from config import COMMISSION_PCT, SLIPPAGE_PCT


def one_side_cost_pct() -> float:
    """Cost of a single leg as a fraction of notional."""
    return (COMMISSION_PCT + SLIPPAGE_PCT) / 100.0


def round_trip_cost_pct() -> float:
    """Total entry+exit cost as a fraction of notional."""
    return one_side_cost_pct() * 2.0


def trade_cost(entry_price: float, exit_price: float, qty: int) -> float:
    """Absolute cost (INR) of a round-trip: entry notional + exit notional, each charged one side."""
    side = one_side_cost_pct()
    return round((entry_price * qty * side) + (exit_price * qty * side), 4)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_costs.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/costs.py tests/test_costs.py
git commit -m "feat: add pure trading-cost model for backtest

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Performance metrics from a trade log + equity curve

**Files:**
- Create: `backtest/metrics.py`
- Test: `tests/test_metrics.py`

The trade log schema used everywhere downstream is:
`symbol, entry_date, exit_date, entry_price, exit_price, qty, gross_pnl, cost, net_pnl, net_pnl_pct, exit_reason`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics.py
"""Tests for performance-metric computation."""
from __future__ import annotations

import pandas as pd

from backtest import metrics


def _trade_log():
    # Two winners (+5%, +3%), one loser (-2%), net pnl already cost-adjusted.
    return pd.DataFrame([
        {"symbol": "A", "net_pnl": 500.0, "net_pnl_pct": 5.0},
        {"symbol": "B", "net_pnl": 300.0, "net_pnl_pct": 3.0},
        {"symbol": "C", "net_pnl": -200.0, "net_pnl_pct": -2.0},
    ])


def _equity_and_counts():
    idx = pd.bdate_range("2026-01-01", periods=5)
    equity = pd.Series([100000, 100500, 100800, 100600, 100600.0], index=idx)
    counts = pd.Series([0, 1, 2, 1, 0], index=idx)
    return equity, counts


def test_basic_counts_and_winrate():
    equity, counts = _equity_and_counts()
    m = metrics.compute_metrics(_trade_log(), equity, counts, start_capital=100000)
    assert m["total_trades"] == 3
    assert m["winners"] == 2
    assert m["losers"] == 1
    assert m["win_rate_pct"] == round(2 / 3 * 100, 2)


def test_profit_factor_and_expectancy_use_net():
    equity, counts = _equity_and_counts()
    m = metrics.compute_metrics(_trade_log(), equity, counts, start_capital=100000)
    # gross profit 800, gross loss 200 -> PF 4.0
    assert m["profit_factor"] == 4.0
    # expectancy = mean net_pnl_pct = (5+3-2)/3
    assert m["expectancy_pct"] == round((5 + 3 - 2) / 3, 2)


def test_drawdown_and_exposure():
    equity, counts = _equity_and_counts()
    m = metrics.compute_metrics(_trade_log(), equity, counts, start_capital=100000)
    # peak 100800 -> trough 100600 => dd = (100600-100800)/100800*100
    assert m["max_drawdown_pct"] == round(abs((100600 - 100800) / 100800 * 100), 2)
    # exposure: 3 of 5 days held >=1 position
    assert m["exposure_pct"] == 60.0


def test_haircut_scales_returns():
    base = {"total_return_pct": 50.0, "cagr_pct": 20.0}
    out = metrics.apply_haircut(base, haircut_pct=20.0)
    assert out["total_return_pct"] == 40.0
    assert out["cagr_pct"] == 16.0


def test_empty_log_is_safe():
    equity, counts = _equity_and_counts()
    m = metrics.compute_metrics(pd.DataFrame(), equity, counts, start_capital=100000)
    assert m["total_trades"] == 0
    assert m["profit_factor"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.metrics'`

- [ ] **Step 3: Write minimal implementation**

```python
# backtest/metrics.py
"""Performance metrics computed from a trade log and an equity curve.

All return-based metrics are derived from the equity curve (which already
reflects costs), so they are not inflated by naive percentage compounding.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _empty_metrics() -> dict:
    return {
        "total_trades": 0, "winners": 0, "losers": 0, "win_rate_pct": 0.0,
        "avg_win_pct": 0.0, "avg_loss_pct": 0.0, "expectancy_pct": 0.0,
        "profit_factor": 0.0, "max_drawdown_pct": 0.0, "total_return_pct": 0.0,
        "cagr_pct": 0.0, "sharpe": 0.0, "exposure_pct": 0.0,
    }


def compute_metrics(trade_log: pd.DataFrame, equity_curve: pd.Series,
                    positions_count: pd.Series, start_capital: float) -> dict:
    """Aggregate performance metrics. ``trade_log`` may be empty."""
    m = _empty_metrics()

    # --- Equity-derived metrics (valid even with no trades) ---
    if len(equity_curve) >= 2:
        running_max = equity_curve.cummax()
        dd = (equity_curve - running_max) / running_max * 100.0
        m["max_drawdown_pct"] = round(abs(dd.min()), 2)

        end_eq = float(equity_curve.iloc[-1])
        m["total_return_pct"] = round((end_eq - start_capital) / start_capital * 100.0, 2)

        days = (equity_curve.index[-1] - equity_curve.index[0]).days
        years = days / 365.25 if days > 0 else 0.0
        if years > 0 and end_eq > 0:
            m["cagr_pct"] = round(((end_eq / start_capital) ** (1 / years) - 1) * 100.0, 2)

        daily_ret = equity_curve.pct_change().dropna()
        if len(daily_ret) > 1 and daily_ret.std() > 0:
            sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(TRADING_DAYS_PER_YEAR)
            m["sharpe"] = round(float(sharpe), 2)

    if len(positions_count) > 0:
        held_days = int((positions_count > 0).sum())
        m["exposure_pct"] = round(held_days / len(positions_count) * 100.0, 2)

    # --- Trade-derived metrics ---
    if trade_log is None or trade_log.empty:
        return m

    total = len(trade_log)
    winners = trade_log[trade_log["net_pnl_pct"] > 0]
    losers = trade_log[trade_log["net_pnl_pct"] <= 0]
    m["total_trades"] = total
    m["winners"] = len(winners)
    m["losers"] = len(losers)
    m["win_rate_pct"] = round(len(winners) / total * 100.0, 2) if total else 0.0
    m["avg_win_pct"] = round(winners["net_pnl_pct"].mean(), 2) if len(winners) else 0.0
    m["avg_loss_pct"] = round(losers["net_pnl_pct"].mean(), 2) if len(losers) else 0.0
    m["expectancy_pct"] = round(trade_log["net_pnl_pct"].mean(), 2)

    gross_profit = winners["net_pnl_pct"].sum()
    gross_loss = abs(losers["net_pnl_pct"].sum())
    m["profit_factor"] = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")
    return m


def apply_haircut(metrics_dict: dict, haircut_pct: float) -> dict:
    """Return a copy with return-based fields scaled down by ``haircut_pct`` percent.

    A blunt sensitivity adjustment for survivorship bias — applied only to
    ``total_return_pct`` and ``cagr_pct``.
    """
    factor = 1.0 - (haircut_pct / 100.0)
    out = dict(metrics_dict)
    for key in ("total_return_pct", "cagr_pct"):
        if key in out:
            out[key] = round(out[key] * factor, 2)
    return out


def format_tearsheet(metrics_dict: dict, title: str = "BACKTEST BASELINE") -> str:
    """Render a metrics dict as a fixed-width text block."""
    pf = metrics_dict["profit_factor"]
    pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
    lines = [
        "=" * 55,
        f"  [{title}]",
        "=" * 55,
        f"  Total Trades   : {metrics_dict['total_trades']}",
        f"  Win Rate       : {metrics_dict['win_rate_pct']:.2f}%",
        f"  Avg Win        : {metrics_dict['avg_win_pct']:+.2f}%",
        f"  Avg Loss       : {metrics_dict['avg_loss_pct']:+.2f}%",
        f"  Expectancy     : {metrics_dict['expectancy_pct']:+.2f}% / trade",
        f"  Profit Factor  : {pf_str}",
        f"  Max Drawdown   : {metrics_dict['max_drawdown_pct']:.2f}%",
        f"  Total Return   : {metrics_dict['total_return_pct']:+.2f}%",
        f"  CAGR           : {metrics_dict['cagr_pct']:+.2f}%",
        f"  Sharpe         : {metrics_dict['sharpe']:.2f}",
        f"  Exposure       : {metrics_dict['exposure_pct']:.2f}% of days",
        "=" * 55,
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_metrics.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/metrics.py tests/test_metrics.py
git commit -m "feat: add equity-curve-based performance metrics + tearsheet

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Portfolio engine — entries fill at next open, capacity cap, equity curve

**Files:**
- Create: `backtest/portfolio_engine.py`
- Test: `tests/test_portfolio_engine.py`

This task builds the engine skeleton: a date-driven loop that queues entry candidates at the close of day *t* and fills them at the **open of day *t+1***, never exceeding `max_positions`, tracking cash and a mark-to-market equity curve. Exits are not yet implemented (positions stay open).

The engine accepts injectable `entry_decision(window, mode) -> bool` and `exit_decision(window, position, max_hold) -> str` so tests can drive it deterministically.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_portfolio_engine.py
"""Tests for the pure portfolio simulation engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import portfolio_engine as pe


def _flat_frame(prices, start="2026-01-01"):
    """OHLCV frame where open==high==low==close==price each day, fixed volume."""
    idx = pd.bdate_range(start, periods=len(prices))
    p = np.array(prices, dtype=float)
    return pd.DataFrame({"open": p, "high": p, "low": p, "close": p,
                         "volume": np.full(len(p), 500000.0)}, index=idx)


def _enrich_stub(df):
    """Attach the indicator columns the position-sizing path reads, with safe values."""
    df = df.copy()
    df["atr"] = 1.0
    return df


def test_entry_fills_at_next_open_not_signal_close():
    # Price rises each day. Signal fires on day index 1 (close), fill must be day 2 open.
    df = _enrich_stub(_flat_frame([100, 101, 102, 103, 104]))
    data = {"AAA": df}

    def entry_on_day1(window, mode):
        return window.index[-1] == df.index[1]   # only signal at the 2nd bar's close

    def never_exit(window, position, max_hold):
        return "HOLD"

    out = pe.simulate(data, start_capital=100000, max_positions=4,
                      warmup=0, entry_decision=entry_on_day1, exit_decision=never_exit)
    # No completed trades (position still open at end), but one position was opened.
    # Verify via equity: cash dropped by qty*open_price(day2)=102*qty at fill.
    assert out["positions_count"].iloc[-1] == 1
    # The fill price recorded is day-2 open (102), proving next-open (not 101 signal close).
    assert out["_debug_last_entry_price"] == 102.0


def test_capacity_cap_respected():
    data = {}
    for i, sym in enumerate(["A", "B", "C", "D", "E"]):
        data[sym] = _enrich_stub(_flat_frame([100, 100, 100, 100, 100]))

    def always_enter(window, mode):
        return True

    def never_exit(window, position, max_hold):
        return "HOLD"

    out = pe.simulate(data, start_capital=100000, max_positions=3,
                      warmup=0, entry_decision=always_enter, exit_decision=never_exit)
    assert out["positions_count"].max() <= 3


def test_no_entry_when_signal_never_fires():
    df = _enrich_stub(_flat_frame([100, 101, 102]))
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: False,
                      exit_decision=lambda w, p, h: "HOLD")
    assert out["positions_count"].max() == 0
    assert out["trade_log"].empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_portfolio_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.portfolio_engine'`

- [ ] **Step 3: Write minimal implementation**

```python
# backtest/portfolio_engine.py
"""Pure, date-driven portfolio backtest engine.

The simulator trades a shared capital account across the whole universe,
respecting a maximum concurrent position count.  It is deliberately free of
network I/O: it consumes a ``{symbol: enriched OHLCV DataFrame}`` dict and
returns a trade log, an equity curve, and a daily position-count series.

Fill model (honest, no look-ahead):
  * Entry signals evaluated on the CLOSE of day t fill at the OPEN of day t+1.
  * Stop-loss / target are resolved intrabar against each day's high/low
    (gap-adjusted to the open).  [Added in Task 4.]
  * Discretionary exit signals (momentum/RSI/time/reversal) fill at the next
    open.  [Added in Task 4.]

Decision functions are injectable for testing.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from config import (
    INITIAL_CAPITAL, MAX_OPEN_POSITIONS, POSITION_RISK_PCT, MAX_HOLD_DAYS,
    STRATEGY_MODE,
)
from strategy.signals import check_entry_signal, check_exit_signal
from strategy.risk import calculate_atr_stop_loss, calculate_target, position_size
from backtest.costs import one_side_cost_pct

TRADE_COLUMNS = [
    "symbol", "entry_date", "exit_date", "entry_price", "exit_price",
    "qty", "gross_pnl", "cost", "net_pnl", "net_pnl_pct", "exit_reason",
]


def _default_entry_decision(window: pd.DataFrame, mode: str) -> bool:
    return check_entry_signal(window, strategy_mode=mode)["signal"]


def _default_exit_decision(window: pd.DataFrame, position: dict, max_hold: int) -> str:
    return check_exit_signal(
        window, entry_price=position["entry_price"], entry_date=position["entry_date"],
        stop_loss=position["stop_loss"], target=position["target"],
        max_hold_days=max_hold, partial_taken=position.get("partial_taken", False),
    )


def _setup_strength(window: pd.DataFrame) -> float:
    """Deterministic ranking key when more candidates than open slots exist.

    Rank by ADX (trend strength) of the latest bar, descending.  Falls back to
    0.0 if ADX is unavailable.
    """
    if "adx" in window.columns:
        val = window["adx"].iloc[-1]
        return float(val) if pd.notna(val) else 0.0
    return 0.0


def simulate(price_data: dict[str, pd.DataFrame], start_capital: float = INITIAL_CAPITAL,
             strategy_mode: str = STRATEGY_MODE, max_positions: int = MAX_OPEN_POSITIONS,
             risk_pct: float = POSITION_RISK_PCT, warmup: int = 200,
             entry_decision=None, exit_decision=None,
             nifty_df: pd.DataFrame | None = None) -> dict:
    """Run the portfolio simulation. Returns trade_log / equity_curve / positions_count."""
    entry_decision = entry_decision or _default_entry_decision
    exit_decision = exit_decision or _default_exit_decision
    side_cost = one_side_cost_pct()

    all_dates = sorted(set().union(*[df.index for df in price_data.values()])) \
        if price_data else []

    cash = float(start_capital)
    positions: dict[str, dict] = {}
    trades: list[dict] = []
    pending_entries: list[str] = []
    equity_records: dict = {}
    count_records: dict = {}
    debug_last_entry_price = None

    def current_equity(date) -> float:
        eq = cash
        for sym, pos in positions.items():
            df = price_data[sym]
            price = df.loc[date, "close"] if date in df.index else pos["entry_price"]
            eq += pos["qty"] * float(price)
        return eq

    for date in all_dates:
        # ---- Phase 1: fill queued entries at TODAY's open ----
        for sym in pending_entries:
            if sym in positions or len(positions) >= max_positions:
                continue
            df = price_data[sym]
            if date not in df.index:
                continue
            entry_price = float(df.loc[date, "open"])
            atr_val = float(df.loc[date, "atr"]) if "atr" in df.columns and pd.notna(df.loc[date, "atr"]) else 0.0
            if atr_val <= 0:
                continue
            stop = calculate_atr_stop_loss(entry_price, atr_value=atr_val)
            target = calculate_target(entry_price, target_pct=0.08)
            equity_now = current_equity(date)
            try:
                qty = position_size(equity_now, entry_price, stop, risk_pct / 100.0)
            except ValueError:
                continue
            # Cap by available cash (plus entry cost).
            affordable = int(cash / (entry_price * (1 + side_cost)))
            qty = min(qty, affordable)
            if qty <= 0:
                continue
            entry_cost = entry_price * qty * side_cost
            cash -= (entry_price * qty + entry_cost)
            positions[sym] = {
                "symbol": sym, "entry_date": date, "entry_price": entry_price,
                "qty": qty, "stop_loss": stop, "target": target,
                "partial_taken": False, "entry_cost": entry_cost,
            }
            debug_last_entry_price = entry_price
        pending_entries = []

        # ---- Phase 3: evaluate signals on TODAY's close, queue for next open ----
        if len(positions) < max_positions:
            candidates = []
            for sym, df in price_data.items():
                if sym in positions:
                    continue
                window = df.loc[:date]
                if len(window) <= warmup or window.index[-1] != date:
                    continue
                if entry_decision(window, strategy_mode):
                    candidates.append((sym, _setup_strength(window)))
            candidates.sort(key=lambda x: x[1], reverse=True)
            slots = max_positions - len(positions)
            pending_entries = [s for s, _ in candidates[:slots]]

        equity_records[date] = current_equity(date)
        count_records[date] = len(positions)

    return {
        "trade_log": pd.DataFrame(trades, columns=TRADE_COLUMNS),
        "equity_curve": pd.Series(equity_records, dtype=float),
        "positions_count": pd.Series(count_records, dtype=float),
        "_debug_last_entry_price": debug_last_entry_price,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_portfolio_engine.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/portfolio_engine.py tests/test_portfolio_engine.py
git commit -m "feat: portfolio engine skeleton with next-open entries and capacity cap

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Portfolio engine — intrabar stop/target + next-open discretionary exits + costs

**Files:**
- Modify: `backtest/portfolio_engine.py`
- Test: `tests/test_portfolio_engine_exits.py`

Add exit handling. Within each day, **after** filling queued entries:
1. **Intrabar stop/target** for held positions, using that day's `low`/`high`, gap-adjusted to the open. Stop is checked **before** target (conservative when both touch in one bar).
2. **Discretionary exits** (anything `check_exit_signal` returns that is not `HOLD`, `TARGET_HIT`, `STOP_LOSS`, or `PARTIAL_EXIT_5PCT`) are evaluated on the close and queued to fill at the **next open**.

Partial exits are intentionally deferred to Task 5.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_portfolio_engine_exits.py
"""Exit-path tests for the portfolio engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import portfolio_engine as pe


def _frame(rows, start="2026-01-01"):
    """rows: list of (open, high, low, close). Volume fixed, atr=1.0 attached."""
    idx = pd.bdate_range(start, periods=len(rows))
    arr = np.array(rows, dtype=float)
    df = pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2],
                       "close": arr[:, 3], "volume": np.full(len(rows), 500000.0)},
                      index=idx)
    df["atr"] = 1.0
    return df


def test_target_hit_closes_position_with_costs():
    # Enter day2 open=100. calculate_target(100,0.08)=108. Day3 high=109 -> target fill 108.
    df = _frame([
        (100, 100, 100, 100),   # day0
        (100, 100, 100, 100),   # day1 (signal close)
        (100, 101, 99, 100),    # day2 entry @ open 100
        (100, 109, 100, 108),   # day3 target hit
        (108, 108, 108, 108),   # day4
    ])

    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=lambda w, p, h: "HOLD")
    log = out["trade_log"]
    assert len(log) == 1
    row = log.iloc[0]
    assert row["exit_reason"] == "TARGET_HIT"
    assert row["entry_price"] == 100.0
    assert row["exit_price"] == 108.0
    # gross = qty*(108-100); cost > 0; net = gross - cost; net_pnl < gross_pnl
    assert row["net_pnl"] < row["gross_pnl"]
    assert row["cost"] > 0


def test_stop_checked_before_target_when_both_touched():
    # calculate_atr_stop_loss(100, atr=1.0, mult 1.5)=98.5 (raw 1.5%). target=108.
    # Day3 both: low=98 (<=98.5 stop) and high=109 (>=108 target). Stop must win.
    df = _frame([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 101, 99, 100),    # entry @100
        (100, 109, 98, 99),     # both stop and target touched
        (99, 99, 99, 99),
    ])
    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=lambda w, p, h: "HOLD")
    row = out["trade_log"].iloc[0]
    assert row["exit_reason"] == "STOP_LOSS"
    assert row["exit_price"] == 98.5    # stop level, no gap (open 100 > stop)


def test_discretionary_exit_fills_next_open():
    df = _frame([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 101, 99, 100),    # entry @100
        (101, 102, 100, 101),   # day3 close -> exit signal fires here
        (105, 106, 104, 105),   # day4 OPEN=105 -> discretionary fill here
    ])

    def exit_on_day3(window, position, max_hold):
        return "MOMENTUM_FADE" if window.index[-1] == df.index[3] else "HOLD"

    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=exit_on_day3)
    row = out["trade_log"].iloc[0]
    assert row["exit_reason"] == "MOMENTUM_FADE"
    assert row["exit_price"] == 105.0   # next-open, not the 101 signal close
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_portfolio_engine_exits.py -v`
Expected: FAIL — exits not implemented; positions never close, `IndexError` on `iloc[0]`.

- [ ] **Step 3: Update the implementation**

In `backtest/portfolio_engine.py`, add a module-level helper above `simulate`:

```python
DISCRETIONARY_EXITS = {"MOMENTUM_FADE", "RSI_OVERBOUGHT", "BEARISH_REVERSAL", "TIME_EXIT"}


def _close_position(positions: dict, trades: list, sym: str, exit_price: float,
                    exit_date, reason: str, side_cost: float) -> float:
    """Book a full exit, append a trade row, and return cash to add back."""
    pos = positions.pop(sym)
    qty = pos["qty"]
    gross = qty * (exit_price - pos["entry_price"])
    exit_cost = exit_price * qty * side_cost
    cost = pos["entry_cost"] + exit_cost
    net = gross - cost
    notional = pos["entry_price"] * qty
    trades.append({
        "symbol": sym, "entry_date": pos["entry_date"], "exit_date": exit_date,
        "entry_price": round(pos["entry_price"], 2), "exit_price": round(exit_price, 2),
        "qty": qty, "gross_pnl": round(gross, 2), "cost": round(cost, 2),
        "net_pnl": round(net, 2),
        "net_pnl_pct": round(net / notional * 100.0, 2) if notional else 0.0,
        "exit_reason": reason,
    })
    return (exit_price * qty) - exit_cost
```

Then, inside `simulate`, add a `pending_exits` list next to `pending_entries`:

```python
    pending_entries: list[str] = []
    pending_exits: list[tuple[str, str]] = []
```

In **Phase 1**, fill queued discretionary exits at today's open *before* filling entries:

```python
        # ---- Phase 1a: fill queued discretionary exits at TODAY's open ----
        for sym, reason in pending_exits:
            if sym not in positions:
                continue
            df = price_data[sym]
            if date not in df.index:
                continue
            cash += _close_position(positions, trades, sym, float(df.loc[date, "open"]),
                                    date, reason, side_cost)
        pending_exits = []
```

After Phase 1 entry filling, add **Phase 2** (intrabar stop/target):

```python
        # ---- Phase 2: intrabar stop/target on TODAY's bar ----
        for sym in list(positions):
            df = price_data[sym]
            if date not in df.index:
                continue
            bar = df.loc[date]
            pos = positions[sym]
            if bar["low"] <= pos["stop_loss"]:
                fill = min(float(bar["open"]), pos["stop_loss"])   # gap down -> open
                cash += _close_position(positions, trades, sym, fill, date, "STOP_LOSS", side_cost)
            elif bar["high"] >= pos["target"]:
                fill = max(float(bar["open"]), pos["target"])      # gap up -> open
                cash += _close_position(positions, trades, sym, fill, date, "TARGET_HIT", side_cost)
```

In **Phase 3**, after queuing entries, also queue discretionary exits:

```python
        # ---- Phase 3b: discretionary exit signals -> queue for next open ----
        for sym, pos in list(positions.items()):
            window = price_data[sym].loc[:date]
            if window.index[-1] != date:
                continue
            reason = exit_decision(window, pos, MAX_HOLD_DAYS)
            if reason in DISCRETIONARY_EXITS:
                pending_exits.append((sym, reason))
```

- [ ] **Step 4: Run tests (new + existing) to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_portfolio_engine.py tests/test_portfolio_engine_exits.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/portfolio_engine.py tests/test_portfolio_engine_exits.py
git commit -m "feat: portfolio engine exits (intrabar stop/target, next-open discretionary) with costs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Partial exits (book 50% at +5%, move stop to breakeven)

**Files:**
- Modify: `backtest/portfolio_engine.py`
- Test: `tests/test_portfolio_engine_partial.py`

When `exit_decision` returns `PARTIAL_EXIT_5PCT` and the position has not yet taken a partial, sell half the quantity at the **next open**, mark `partial_taken=True`, and raise the stop to the entry price (breakeven). The partial sale is recorded as its own trade row with reason `PARTIAL_EXIT_50%`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_portfolio_engine_partial.py
"""Partial-exit tests for the portfolio engine."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import portfolio_engine as pe


def _frame(rows, start="2026-01-01"):
    idx = pd.bdate_range(start, periods=len(rows))
    arr = np.array(rows, dtype=float)
    df = pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2],
                       "close": arr[:, 3], "volume": np.full(len(rows), 500000.0)},
                      index=idx)
    df["atr"] = 1.0
    return df


def test_partial_books_half_and_moves_stop_to_breakeven():
    df = _frame([
        (100, 100, 100, 100),
        (100, 100, 100, 100),
        (100, 101, 99, 100),    # entry @100, qty Q
        (105, 106, 104, 105),   # day3 close -> +5% -> partial signal fires
        (106, 107, 105, 106),   # day4 OPEN=106 -> partial fills here
        (106, 106, 106, 106),
    ])

    def partial_day3(window, position, max_hold):
        if window.index[-1] == df.index[3] and not position.get("partial_taken"):
            return "PARTIAL_EXIT_5PCT"
        return "HOLD"

    out = pe.simulate({"AAA": df}, start_capital=100000, warmup=0,
                      entry_decision=lambda w, m: w.index[-1] == df.index[1],
                      exit_decision=partial_day3)
    log = out["trade_log"]
    partials = log[log["exit_reason"] == "PARTIAL_EXIT_50%"]
    assert len(partials) == 1
    assert partials.iloc[0]["exit_price"] == 106.0
    # Still holding the remaining half at the end (no further exit signal).
    assert out["positions_count"].iloc[-1] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_portfolio_engine_partial.py -v`
Expected: FAIL — partial reason ignored, no `PARTIAL_EXIT_50%` row.

- [ ] **Step 3: Update the implementation**

Add a helper above `simulate`:

```python
def _book_partial(positions: dict, trades: list, sym: str, exit_price: float,
                  exit_date, side_cost: float) -> float:
    """Sell half the position, move stop to breakeven, return cash to add back."""
    pos = positions[sym]
    half = max(1, pos["qty"] // 2)
    gross = half * (exit_price - pos["entry_price"])
    exit_cost = exit_price * half * side_cost
    notional = pos["entry_price"] * half
    trades.append({
        "symbol": sym, "entry_date": pos["entry_date"], "exit_date": exit_date,
        "entry_price": round(pos["entry_price"], 2), "exit_price": round(exit_price, 2),
        "qty": half, "gross_pnl": round(gross, 2), "cost": round(exit_cost, 2),
        "net_pnl": round(gross - exit_cost, 2),
        "net_pnl_pct": round((gross - exit_cost) / notional * 100.0, 2) if notional else 0.0,
        "exit_reason": "PARTIAL_EXIT_50%",
    })
    pos["qty"] -= half
    pos["partial_taken"] = True
    pos["stop_loss"] = pos["entry_price"]   # breakeven
    return (exit_price * half) - exit_cost
```

Add `PARTIAL_EXIT_5PCT` handling to the **Phase 1a** queued-exit filling (a partial is queued just like a discretionary exit, but routed to `_book_partial`):

```python
        # ---- Phase 1a: fill queued exits at TODAY's open ----
        for sym, reason in pending_exits:
            if sym not in positions:
                continue
            df = price_data[sym]
            if date not in df.index:
                continue
            open_px = float(df.loc[date, "open"])
            if reason == "PARTIAL_EXIT_5PCT":
                cash += _book_partial(positions, trades, sym, open_px, date, side_cost)
            else:
                cash += _close_position(positions, trades, sym, open_px, date, reason, side_cost)
        pending_exits = []
```

Extend **Phase 3b** to also queue partials:

```python
        # ---- Phase 3b: exit signals -> queue for next open ----
        for sym, pos in list(positions.items()):
            window = price_data[sym].loc[:date]
            if window.index[-1] != date:
                continue
            reason = exit_decision(window, pos, MAX_HOLD_DAYS)
            if reason in DISCRETIONARY_EXITS:
                pending_exits.append((sym, reason))
            elif reason == "PARTIAL_EXIT_5PCT" and not pos.get("partial_taken"):
                pending_exits.append((sym, reason))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_portfolio_engine_partial.py tests/test_portfolio_engine.py tests/test_portfolio_engine_exits.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/portfolio_engine.py tests/test_portfolio_engine_partial.py
git commit -m "feat: portfolio engine partial exits at next open with breakeven stop

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Survivorship haircut config + runner that wires data → engine → tear-sheet

**Files:**
- Modify: `config.py` (add `SURVIVORSHIP_HAIRCUT_PCT`)
- Create: `backtest/run_portfolio.py`
- Modify: `main.py`
- Test: `tests/test_run_portfolio.py`

The runner is the only piece that touches the network. It is kept thin and tested with an **injected loader** so no real Yahoo calls happen in tests.

- [ ] **Step 1: Add the config constant**

In `config.py`, in the Backtest section (after `MAX_HOLD_DAYS`), add:

```python
SURVIVORSHIP_HAIRCUT_PCT: float = 20.0     # blunt downward adjustment to returns for survivorship bias
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_run_portfolio.py
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_run_portfolio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.run_portfolio'`

- [ ] **Step 4: Write the implementation**

```python
# backtest/run_portfolio.py
"""Thin runner: load the universe, enrich, simulate, report.

This is the only backtest module that performs network I/O.  The data loader
is injectable so tests can run without Yahoo Finance.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from config import (
    WATCHLIST, INITIAL_CAPITAL, STRATEGY_MODE, MAX_OPEN_POSITIONS,
    POSITION_RISK_PCT, STRICT_MIN_AVG_VOLUME, RELAXED_MIN_AVG_VOLUME,
    SURVIVORSHIP_HAIRCUT_PCT,
)
from broker.zerodha_api import get_ohlcv_free
from strategy.indicators import enrich_with_indicators
from backtest.portfolio_engine import simulate
from backtest import metrics as metrics_mod

MIN_BARS = 250


def load_universe(watchlist: list[str], days: int, loader, strategy_mode: str) -> dict:
    """Fetch + enrich every symbol that passes the liquidity/length filters."""
    min_volume = STRICT_MIN_AVG_VOLUME if strategy_mode == "STRICT" else RELAXED_MIN_AVG_VOLUME
    data: dict[str, pd.DataFrame] = {}
    for sym in watchlist:
        try:
            df = loader(sym, days)
        except Exception as exc:                       # noqa: BLE001 - network resilience
            print(f"  [!] {sym}: load failed ({exc})")
            continue
        if df is None or len(df) < MIN_BARS:
            continue
        if df["volume"].tail(20).mean() < min_volume:
            continue
        data[sym] = enrich_with_indicators(df)
    return data


def run(watchlist: list[str] | None = None, days: int = 1200, loader=get_ohlcv_free,
        strategy_mode: str = STRATEGY_MODE, save_csv: bool = False,
        csv_path: str = "trades_log_portfolio.csv", entry_decision=None,
        exit_decision=None) -> dict:
    """Run a portfolio backtest and return metrics + trade log."""
    watchlist = watchlist if watchlist is not None else WATCHLIST
    data = load_universe(watchlist, days, loader, strategy_mode)

    sim = simulate(data, start_capital=INITIAL_CAPITAL, strategy_mode=strategy_mode,
                   max_positions=MAX_OPEN_POSITIONS, risk_pct=POSITION_RISK_PCT,
                   entry_decision=entry_decision, exit_decision=exit_decision)

    m = metrics_mod.compute_metrics(sim["trade_log"], sim["equity_curve"],
                                    sim["positions_count"], INITIAL_CAPITAL)
    m_hair = metrics_mod.apply_haircut(m, SURVIVORSHIP_HAIRCUT_PCT)

    if save_csv and not sim["trade_log"].empty:
        sim["trade_log"].to_csv(csv_path, index=False)

    return {"trade_log": sim["trade_log"], "equity_curve": sim["equity_curve"],
            "metrics": m, "metrics_haircut": m_hair}


def main() -> None:
    result = run(save_csv=True)
    print(metrics_mod.format_tearsheet(result["metrics"], "BACKTEST BASELINE (gross of survivorship)"))
    print(metrics_mod.format_tearsheet(result["metrics_haircut"],
                                       f"AFTER {int(__import__('config').SURVIVORSHIP_HAIRCUT_PCT)}% SURVIVORSHIP HAIRCUT"))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_run_portfolio.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Point `main.py` at the portfolio runner**

Replace the entire contents of `main.py` with:

```python
"""Main entry-point for the swing trading backtest system.

Usage::

    python main.py

Loads daily OHLCV for every symbol in ``config.WATCHLIST`` from Yahoo Finance,
runs the portfolio-level backtest, and prints the baseline tear-sheet.
"""

from backtest.run_portfolio import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Commit**

```bash
git add config.py backtest/run_portfolio.py main.py tests/test_run_portfolio.py
git commit -m "feat: portfolio backtest runner + survivorship haircut; repoint main.py

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Walk-forward with strict non-overlapping splits + OOS pass/fail

**Files:**
- Rewrite: `backtest/walk_forward.py`
- Test: `tests/test_walk_forward.py`

The reworked walk-forward slices each symbol's **enriched** data into contiguous, non-overlapping segments by row position, runs the portfolio engine on each, and flags failure when an out-of-sample segment's profit factor falls below `OOS_MIN_PF_RATIO` times the in-sample profit factor.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_walk_forward.py
"""Tests for the strict walk-forward verdict logic."""
from __future__ import annotations

from backtest import walk_forward as wf


def test_verdict_passes_when_oos_holds():
    # in-sample PF 2.0, OOS PFs 1.8 and 1.6; ratio floor 0.6 -> need >= 1.2. Both pass.
    verdict = wf.evaluate_segments(in_sample_pf=2.0, oos_pfs=[1.8, 1.6], min_ratio=0.6)
    assert verdict["passed"] is True


def test_verdict_fails_on_oos_degradation():
    # OOS PF 0.9 < 1.2 floor -> fail.
    verdict = wf.evaluate_segments(in_sample_pf=2.0, oos_pfs=[1.8, 0.9], min_ratio=0.6)
    assert verdict["passed"] is False
    assert 1 in verdict["failed_segments"]   # second OOS segment (index 1) failed


def test_split_indices_are_non_overlapping():
    # 300 rows, 3 segments -> [(0,100),(100,200),(200,300)] contiguous, no overlap.
    segs = wf.split_indices(total=300, n_segments=3)
    assert segs == [(0, 100), (100, 200), (200, 300)]
    for (a_start, a_end), (b_start, b_end) in zip(segs, segs[1:]):
        assert a_end == b_start
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_walk_forward.py -v`
Expected: FAIL — `AttributeError`/`ImportError` (functions do not exist yet).

- [ ] **Step 3: Rewrite `backtest/walk_forward.py`**

```python
# backtest/walk_forward.py
"""Strict walk-forward validation over the portfolio engine.

Splits each symbol's enriched history into contiguous, non-overlapping
segments.  Segment 0 is in-sample; the rest are out-of-sample.  The strategy
is declared robust only if every out-of-sample segment's profit factor stays
within ``OOS_MIN_PF_RATIO`` of the in-sample profit factor.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from config import (
    WATCHLIST, INITIAL_CAPITAL, STRATEGY_MODE, MAX_OPEN_POSITIONS, POSITION_RISK_PCT,
)
from broker.zerodha_api import get_ohlcv_free
from strategy.indicators import enrich_with_indicators
from backtest.portfolio_engine import simulate
from backtest import metrics as metrics_mod

N_SEGMENTS = 3
OOS_MIN_PF_RATIO = 0.6


def split_indices(total: int, n_segments: int = N_SEGMENTS) -> list[tuple[int, int]]:
    """Contiguous, non-overlapping ``(start, end)`` row ranges covering ``total`` rows."""
    size = total // n_segments
    bounds = []
    for i in range(n_segments):
        start = i * size
        end = total if i == n_segments - 1 else (i + 1) * size
        bounds.append((start, end))
    return bounds


def evaluate_segments(in_sample_pf: float, oos_pfs: list[float],
                      min_ratio: float = OOS_MIN_PF_RATIO) -> dict:
    """Pass/fail verdict: each OOS profit factor must be >= min_ratio * in-sample PF."""
    floor = in_sample_pf * min_ratio
    failed = [i for i, pf in enumerate(oos_pfs) if pf < floor]
    return {"passed": len(failed) == 0, "floor": round(floor, 2),
            "failed_segments": failed}


def _segment_pf(data_slice: dict) -> float:
    sim = simulate(data_slice, start_capital=INITIAL_CAPITAL, strategy_mode=STRATEGY_MODE,
                   max_positions=MAX_OPEN_POSITIONS, risk_pct=POSITION_RISK_PCT)
    m = metrics_mod.compute_metrics(sim["trade_log"], sim["equity_curve"],
                                    sim["positions_count"], INITIAL_CAPITAL)
    pf = m["profit_factor"]
    return 999.0 if pf == float("inf") else pf


def run(watchlist: list[str] | None = None, days: int = 1200,
        loader=get_ohlcv_free) -> dict:
    """Run the full walk-forward and print per-segment profit factors + verdict."""
    watchlist = watchlist if watchlist is not None else WATCHLIST
    enriched: dict[str, pd.DataFrame] = {}
    for sym in watchlist:
        try:
            df = loader(sym, days)
        except Exception:                              # noqa: BLE001
            continue
        if df is None or len(df) < 250:
            continue
        enriched[sym] = enrich_with_indicators(df)

    if not enriched:
        print("  [!] No data loaded for walk-forward.")
        return {"passed": False, "segment_pfs": []}

    min_len = min(len(df) for df in enriched.values())
    bounds = split_indices(min_len, N_SEGMENTS)

    segment_pfs = []
    for seg_i, (start, end) in enumerate(bounds):
        data_slice = {s: df.iloc[start:end] for s, df in enriched.items()}
        pf = _segment_pf(data_slice)
        segment_pfs.append(pf)
        label = "IN-SAMPLE" if seg_i == 0 else f"OOS #{seg_i}"
        print(f"  Segment {seg_i} [{label}] rows {start}:{end} -> profit factor {pf:.2f}")

    verdict = evaluate_segments(segment_pfs[0], segment_pfs[1:])
    print("\n  " + ("[PASS] Strategy holds out-of-sample." if verdict["passed"]
                    else f"[FAIL] OOS degradation in segments {verdict['failed_segments']} "
                         f"(floor PF {verdict['floor']})."))
    return {"passed": verdict["passed"], "segment_pfs": segment_pfs}


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_walk_forward.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/walk_forward.py tests/test_walk_forward.py
git commit -m "feat: strict non-overlapping walk-forward with OOS pass/fail verdict

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Forward paper-test running-equity persistence

**Files:**
- Modify: `paper_trade/paper_engine.py`
- Test: `tests/test_paper_equity.py`

Give the paper engine a persistent equity figure so the 4-week forward test accumulates real P&L across runs instead of resetting each day. Add pure helpers `load_portfolio_state` / `save_portfolio_state` / `apply_realized_pnl` and a `paper_trades/portfolio_state.json` store. The daily job updates equity whenever a trade closes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paper_equity.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_paper_equity.py -v`
Expected: FAIL — `AttributeError: module 'paper_trade.paper_engine' has no attribute 'apply_realized_pnl'`.

- [ ] **Step 3: Add the helpers to `paper_trade/paper_engine.py`**

Near the other path constants (after `CLOSED_TRADES_FILE`), add:

```python
PORTFOLIO_STATE_FILE = os.path.join(PAPER_DIR, "portfolio_state.json")
```

Then add these pure functions (place them after `save_open_positions`):

```python
def load_portfolio_state(path: str = PORTFOLIO_STATE_FILE) -> dict:
    """Load the running forward-test equity, defaulting to the starting capital."""
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return {"equity": float(data.get("equity", INITIAL_CAPITAL)),
                    "realized_pnl": float(data.get("realized_pnl", 0.0))}
        except (json.JSONDecodeError, ValueError):
            pass
    return {"equity": float(INITIAL_CAPITAL), "realized_pnl": 0.0}


def save_portfolio_state(state: dict, path: str = PORTFOLIO_STATE_FILE) -> None:
    with open(path, "w") as f:
        json.dump(state, f, indent=4)


def apply_realized_pnl(state: dict, pnl_amount: float) -> dict:
    """Return a new state with ``pnl_amount`` (INR) added to equity and realized P&L."""
    return {"equity": round(state["equity"] + pnl_amount, 2),
            "realized_pnl": round(state["realized_pnl"] + pnl_amount, 2)}
```

- [ ] **Step 4: Wire it into `run_daily_job`**

At the start of `run_daily_job`, after `positions = load_open_positions()`, add:

```python
    portfolio_state = load_portfolio_state()
```

In the **full exit** branch (where `reason != "HOLD"` and a trade closes), after computing `pnl_pct`, convert to rupees on the booked quantity and update state:

```python
            pnl_amount = (latest_close - pos["entry_price"]) * pos["qty"]
            portfolio_state = apply_realized_pnl(portfolio_state, pnl_amount)
```

In the **partial exit** branch, after booking the 50%:

```python
            pnl_amount = (latest_close - pos["entry_price"]) * pos["qty"]
            portfolio_state = apply_realized_pnl(portfolio_state, pnl_amount)
```

Before the dashboard print (after `save_open_positions(positions)`), persist and surface it:

```python
    save_portfolio_state(portfolio_state)
```

And add one line to the dashboard block:

```python
    print(f"   Forward Equity : {portfolio_state['equity']:,.2f} "
          f"(realized {portfolio_state['realized_pnl']:+,.2f})")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_paper_equity.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add paper_trade/paper_engine.py tests/test_paper_equity.py
git commit -m "feat: persistent forward-test equity in paper engine

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Full-suite verification + documentation refresh

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/specs/2026-06-21-strategy-validation-design.md` (mark Phase 1 built)

- [ ] **Step 1: Run the entire test suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — all prior tests (28) plus the new ones (costs 3, metrics 6, engine 3, exits 3, partial 1, runner 2, walk-forward 3, paper equity 3) = **52 passed**.

- [ ] **Step 2: Update `README.md` Usage section**

Replace the "Historical Backtesting" subsection body with:

```markdown
### 2. Historical Backtesting (portfolio-level)
Runs a single shared-capital account across the whole watchlist, respecting the
max concurrent position cap, filling entries at the next day's open, and charging
commission + slippage. Prints the baseline tear-sheet (and a survivorship-haircut copy).
```python
python main.py
```
For the out-of-sample robustness check:
```python
python -m backtest.walk_forward
```
```

- [ ] **Step 3: Update `CLAUDE.md`**

In the "Architecture" section, add bullet lines for the new modules:

```markdown
- **backtest/portfolio_engine.py** — pure date-driven portfolio simulator (shared capital,
  position cap, next-open fills, intrabar stop/target, costs). Injectable entry/exit fns.
- **backtest/costs.py / metrics.py** — trading-cost model and equity-curve metrics + tear-sheet.
- **backtest/run_portfolio.py** — thin runner (network I/O lives here); `main.py` calls it.
```

In the "Known gotchas" section, remove the "Paper engine has no capital persistence" sentence's first clause about backtest capital (the portfolio engine now models it) and note the forward-test equity store at `paper_trades/portfolio_state.json`.

- [ ] **Step 4: Mark Phase 1 status in the spec**

At the top of `docs/superpowers/specs/2026-06-21-strategy-validation-design.md`, change the Status line to:

```markdown
**Status:** Phase 1 implemented; Phases 2–3 pending
```

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/superpowers/specs/2026-06-21-strategy-validation-design.md
git commit -m "docs: refresh README/CLAUDE/spec for portfolio backtest (Phase 1 built)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 6: Run a real smoke backtest (manual, network)**

Run: `.venv/Scripts/python.exe main.py`
Expected: a printed tear-sheet with non-error output. Numbers are expected to be **lower** than the old per-symbol engine. Note the baseline figures — this is the trusted baseline Phase 2 will build on. (This step needs internet; if Yahoo is unreachable, retry later — no code change required.)

---

## Self-review against the spec

- **Portfolio-level engine** (spec §1) → Tasks 3, 4, 5.
- **Realistic next-open fills + intrabar stop/target, stop-before-target** (spec §2) → Task 4.
- **Costs & slippage from config** (spec §3) → Tasks 1, 4, 5.
- **Survivorship handling: document + haircut + broader-universe sanity** (spec §4) → Task 6 (haircut + config), README/CLAUDE doc note in Task 9; broader-universe sanity is run-time (pass an alternate `watchlist` to `run`).
- **Walk-forward as headline, strict splits, OOS pass/fail** (spec §5) → Task 7.
- **Trusted tear-sheet after costs** (spec §6) → Tasks 2, 6.
- **Forward paper-test running equity + gate** (spec §7) → Task 8 (equity persistence); the go/no-go comparison is a manual read of forward equity vs. baseline expectancy printed by Task 6.
- **Testing** (spec) → every task is TDD; Task 9 verifies the full suite.
- **YAGNI exclusions** honored: no new indicators, no broker orders, no point-in-time data, no parameter tuning.

No placeholders remain; type/name usage (`simulate` return keys, `TRADE_COLUMNS`, `compute_metrics` signature, `apply_haircut`, `evaluate_segments`, `split_indices`, `load_portfolio_state`/`apply_realized_pnl`) is consistent across tasks.
