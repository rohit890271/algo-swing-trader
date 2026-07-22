"""Score the forward paper test with the backtest's own metrics code.

The point of the forward test is to compare live-scanned results against the
validated backtest config on equal terms.  That only works if both are scored
identically, so this reads the paper engine's artifacts and hands them to
``backtest.metrics.compute_metrics`` -- the same function that produced the
numbers in ``docs/RESEARCH_LOG.md``.

Read the caveats it prints.  A handful of forward trades cannot confirm or
refute an edge; this reports what happened, not whether to deploy.

Usage::

    python -m paper_trade.forward_report
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from config import INITIAL_CAPITAL
from backtest import metrics as metrics_mod
from paper_trade.paper_engine import (
    load_equity_curve, load_closed_trades, load_open_positions,
    load_portfolio_state, load_pending,
)

# Backtest reference for the adopted H1+H2 config (docs/RESEARCH_LOG.md).
# Comparison anchor only -- it was measured on a different period and universe.
BACKTEST_REFERENCE = {
    "win_rate_pct": 66.0,
    "profit_factor": 2.9,
    "cagr_pct": 5.2,
    "max_drawdown_pct": 8.4,
    "mar_ratio": 0.62,
    "sharpe": 0.95,
}

MIN_TRADES_FOR_SIGNAL = 30   # below this, forward stats are anecdote


def build_report() -> dict:
    """Compute forward metrics from the persisted paper-trade artifacts."""
    equity = load_equity_curve()
    trades = load_closed_trades()
    # The paper engine records one equity point per scanned bar, so exposure
    # is derived from the trade log rather than a per-day position count.
    positions_count = pd.Series(dtype=float)
    m = metrics_mod.compute_metrics(trades, equity, positions_count, INITIAL_CAPITAL)
    return {"metrics": m, "trades": trades, "equity": equity}


def format_report(report: dict) -> str:
    m = report["metrics"]
    equity = report["equity"]
    trades = report["trades"]
    state = load_portfolio_state()
    positions = load_open_positions()
    pending = load_pending()

    lines = ["=" * 62, "  [FORWARD PAPER TEST]", "=" * 62]

    if len(equity) == 0:
        lines += ["  No equity history yet -- run the paper engine first.",
                  "=" * 62]
        return "\n".join(lines)

    start, end = equity.index[0].date(), equity.index[-1].date()
    sessions = len(equity)
    lines += [
        f"  Period         : {start} -> {end}  ({sessions} sessions)",
        f"  Equity         : {equity.iloc[-1]:,.2f}  (start {INITIAL_CAPITAL:,.2f})",
        f"  Total Return   : {m['total_return_pct']:+.2f}%",
        f"  Free Cash      : {state['cash']:,.2f}",
        f"  Open Positions : {len(positions)}"
        f"  |  queued: {len(pending['entries'])} in / {len(pending['exits'])} out",
        "-" * 62,
        f"  Closed Trades  : {m['total_trades']}",
        f"  Win Rate       : {m['win_rate_pct']:.2f}%",
        f"  Profit Factor  : {metrics_mod._fmt_mar(m['profit_factor'])}",
        f"  Expectancy     : {m['expectancy_pct']:+.2f}% / trade",
        f"  Max Drawdown   : {m['max_drawdown_pct']:.2f}%",
        f"  Sharpe         : {m['sharpe']:.2f}",
        "-" * 62,
    ]

    # Only the trade-level stats are meaningful this early; annualised figures
    # from a few weeks of data are extrapolation, not measurement.
    if sessions < 60:
        lines += [
            "  CAGR / MAR are NOT shown: annualising a few weeks of equity",
            "  produces a meaningless number in either direction.",
            "-" * 62,
        ]
    else:
        lines += [f"  CAGR           : {m['cagr_pct']:+.2f}%",
                  f"  MAR Ratio      : {metrics_mod._fmt_mar(m['mar_ratio'])}",
                  "-" * 62]

    lines += ["  vs BACKTEST (H1+H2 adopted config)",
              f"    win rate      : {m['win_rate_pct']:.1f}% forward "
              f"vs {BACKTEST_REFERENCE['win_rate_pct']:.1f}% backtest",
              f"    profit factor : {metrics_mod._fmt_mar(m['profit_factor'])} forward "
              f"vs {BACKTEST_REFERENCE['profit_factor']:.2f} backtest"]

    if m["total_trades"] < MIN_TRADES_FOR_SIGNAL:
        lines += [
            "-" * 62,
            f"  [!] {m['total_trades']} closed trades is below the "
            f"{MIN_TRADES_FOR_SIGNAL}-trade floor.",
            "      These numbers are anecdote, not evidence. A 60% win rate over",
            "      10 trades is entirely consistent with a strategy that has no",
            "      edge at all. Do not size up on this.",
        ]

    if not trades.empty:
        lines += ["-" * 62, "  RECENT TRADES"]
        for _, t in trades.tail(8).iterrows():
            lines.append(f"    {str(t['symbol']):<12} {t['entry_date']} -> {t['exit_date']}  "
                         f"{float(t['net_pnl_pct']):+6.2f}%  {t['exit_reason']}")

    lines.append("=" * 62)
    return "\n".join(lines)


def main() -> None:
    print(format_report(build_report()))


if __name__ == "__main__":
    main()
