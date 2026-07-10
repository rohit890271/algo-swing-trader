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
        "cagr_pct": 0.0, "mar_ratio": 0.0, "sharpe": 0.0, "exposure_pct": 0.0,
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

        # MAR / Calmar ratio: CAGR over max drawdown — the headline
        # risk-adjusted-return figure for Phase 2 experiments.
        if m["max_drawdown_pct"] > 0:
            m["mar_ratio"] = round(m["cagr_pct"] / m["max_drawdown_pct"], 2)
        elif m["cagr_pct"] > 0:
            m["mar_ratio"] = float("inf")

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


def _fmt_mar(mar: float) -> str:
    """Format the MAR ratio, tolerating the infinite (zero-drawdown) case."""
    return "inf" if mar == float("inf") else f"{mar:.2f}"


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
        f"  MAR (Calmar)   : {_fmt_mar(metrics_dict['mar_ratio'])}",
        f"  Sharpe         : {metrics_dict['sharpe']:.2f}",
        f"  Exposure       : {metrics_dict['exposure_pct']:.2f}% of days",
        "=" * 55,
    ]
    return "\n".join(lines)
