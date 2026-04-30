"""
Run backtests for both STRICT and RELAXED strategy modes and compare results.

This script executes two separate backtests:
1. STRICT mode: Current settings with strict entry criteria
2. RELAXED mode: Easier entry criteria for more frequent trades

Target: RELAXED mode should generate 150-200 trades over 4 years (~1 trade per 7 days)
"""

import sys
import os

# Ensure the project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from backtest.engine import run_backtest
from config import WATCHLIST


def print_comparison(strict_results, relaxed_results):
    """Print a side-by-side comparison of both modes."""
    strict_summary = strict_results["summary"]
    relaxed_summary = relaxed_results["summary"]
    strict_trades = strict_results["trade_log"]
    relaxed_trades = relaxed_results["trade_log"]

    print("\n" + "=" * 80)
    print("  [STRATEGY MODE COMPARISON]")
    print("=" * 80)

    print(f"\n  {'METRIC':<30} {'STRICT':<20} {'RELAXED':<20} {'CHANGE':<15}")
    print("  " + "-" * 80)

    # Total trades
    strict_total = strict_summary["total_trades"]
    relaxed_total = relaxed_summary["total_trades"]
    trade_change = relaxed_total - strict_total
    trade_pct = ((relaxed_total - strict_total) / strict_total * 100) if strict_total > 0 else 0
    print(f"  {'Total Trades':<30} {strict_total:<20} {relaxed_total:<20} {trade_change:+d} ({trade_pct:+.1f}%)")

    # Win rate
    strict_wr = strict_summary["win_rate_pct"]
    relaxed_wr = relaxed_summary["win_rate_pct"]
    wr_change = relaxed_wr - strict_wr
    print(f"  {'Win Rate (%)':<30} {strict_wr:<20.2f} {relaxed_wr:<20.2f} {wr_change:+.2f}%")

    # Average profit
    strict_profit = strict_summary["avg_profit_pct"]
    relaxed_profit = relaxed_summary["avg_profit_pct"]
    profit_change = relaxed_profit - strict_profit
    print(f"  {'Avg Profit (win) (%)':<30} {strict_profit:<20.2f} {relaxed_profit:<20.2f} {profit_change:+.2f}%")

    # Average loss
    strict_loss = strict_summary["avg_loss_pct"]
    relaxed_loss = relaxed_summary["avg_loss_pct"]
    loss_change = relaxed_loss - strict_loss
    print(f"  {'Avg Loss (loss) (%)':<30} {strict_loss:<20.2f} {relaxed_loss:<20.2f} {loss_change:+.2f}%")

    # Profit factor
    strict_pf = strict_summary.get("profit_factor", 0)
    relaxed_pf = relaxed_summary.get("profit_factor", 0)
    strict_pf_str  = f"{strict_pf:.2f}"  if strict_pf  != float('inf') else "inf"
    relaxed_pf_str = f"{relaxed_pf:.2f}" if relaxed_pf != float('inf') else "inf"
    pf_change = ""
    if strict_pf != float('inf') and relaxed_pf != float('inf'):
        pf_change = f"{relaxed_pf - strict_pf:+.2f}"
    print(f"  {'Profit Factor':<30} {strict_pf_str:<20} {relaxed_pf_str:<20} {pf_change:<15}")

    # Max drawdown
    strict_dd = strict_summary["max_drawdown_pct"]
    relaxed_dd = relaxed_summary["max_drawdown_pct"]
    dd_change = relaxed_dd - strict_dd
    print(f"  {'Max Drawdown (%)':<30} {strict_dd:<20.2f} {relaxed_dd:<20.2f} {dd_change:+.2f}%")

    # Total return
    strict_return = strict_summary["total_return_pct"]
    relaxed_return = relaxed_summary["total_return_pct"]
    return_change = relaxed_return - strict_return
    print(f"  {'Total Return (%)':<30} {strict_return:<20.2f} {relaxed_return:<20.2f} {return_change:+.2f}%")

    print("  " + "-" * 80)

    # Trade frequency analysis
    print(f"\n  [TRADE FREQUENCY ANALYSIS]")
    print("  " + "-" * 80)

    if not strict_trades.empty:
        strict_trades["entry_date"] = pd.to_datetime(strict_trades["entry_date"])
        strict_days = (strict_trades["entry_date"].max() - strict_trades["entry_date"].min()).days
        strict_freq = strict_days / strict_total if strict_total > 0 else 0
        print(f"  STRICT: {strict_total} trades over {strict_days} days = 1 trade every {strict_freq:.1f} days")

    if not relaxed_trades.empty:
        relaxed_trades["entry_date"] = pd.to_datetime(relaxed_trades["entry_date"])
        relaxed_days = (relaxed_trades["entry_date"].max() - relaxed_trades["entry_date"].min()).days
        relaxed_freq = relaxed_days / relaxed_total if relaxed_total > 0 else 0
        print(f"  RELAXED: {relaxed_total} trades over {relaxed_days} days = 1 trade every {relaxed_freq:.1f} days")

    print("  " + "-" * 80)

    # Target assessment
    print(f"\n  [TARGET ASSESSMENT]")
    print("  " + "-" * 80)
    target_min = 150
    target_max = 200
    target_freq = 7.0  # 1 trade per 7 days

    if relaxed_total >= target_min and relaxed_total <= target_max:
        print(f"  [PASS] RELAXED mode target MET: {relaxed_total} trades (target: {target_min}-{target_max})")
    elif relaxed_total < target_min:
        print(f"  [WARN] RELAXED mode below target: {relaxed_total} trades (target: {target_min}-{target_max})")
    else:
        print(f"  [WARN] RELAXED mode above target: {relaxed_total} trades (target: {target_min}-{target_max})")

    if not relaxed_trades.empty:
        relaxed_trades["entry_date"] = pd.to_datetime(relaxed_trades["entry_date"])
        relaxed_days = (relaxed_trades["entry_date"].max() - relaxed_trades["entry_date"].min()).days
        relaxed_freq = relaxed_days / relaxed_total if relaxed_total > 0 else 0
        if relaxed_freq <= target_freq + 1.0:  # Allow 1 day tolerance
            print(f"  [PASS] Frequency target MET: 1 trade every {relaxed_freq:.1f} days (target: {target_freq} days)")
        else:
            print(f"  [WARN] Frequency below target: 1 trade every {relaxed_freq:.1f} days (target: {target_freq} days)")

    print("  " + "-" * 80)
    print("=" * 80)


if __name__ == "__main__":
    import pandas as pd

    print("\n" + "=" * 80)
    print("  [RUNNING BACKTEST COMPARISON]")
    print("=" * 80)

    # Run STRICT mode backtest
    print("\n" + "=" * 80)
    print("  [RUNNING STRICT MODE BACKTEST]")
    print("=" * 80)
    strict_results = run_backtest(
        watchlist=WATCHLIST,
        days=1200,
        save_csv=True,
        csv_path="trades_log_strict.csv",
        strategy_mode="STRICT"
    )

    # Run RELAXED mode backtest
    print("\n" + "=" * 80)
    print("  [RUNNING RELAXED MODE BACKTEST]")
    print("=" * 80)
    relaxed_results = run_backtest(
        watchlist=WATCHLIST,
        days=1200,
        save_csv=True,
        csv_path="trades_log_relaxed.csv",
        strategy_mode="RELAXED"
    )

    # Print comparison
    print_comparison(strict_results, relaxed_results)

    print("\n  [CSV FILES SAVED]")
    print("  - trades_log_strict.csv (STRICT mode)")
    print("  - trades_log_relaxed.csv (RELAXED mode)")
    print("=" * 80 + "\n")
