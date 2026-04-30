"""
Targeted bisect: test RELAXED_PULLBACK_MIN at 3.5% to land between 180-220 trades.
Runs as a standalone fresh-interpreter script (no importlib tricks needed).
"""

from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

import config

TARGET_LOW  = 180
TARGET_HIGH = 220

def run_and_report(pullback_min: float) -> tuple[int, dict]:
    """Override pullback min, run backtest, return (trades, summary)."""
    # Patch at module level BEFORE any strategy imports happen
    config.RELAXED_PULLBACK_MIN = pullback_min

    # Import engine fresh each call isn't possible in-process for signals.py,
    # but since this whole script is run fresh each time, it IS fresh.
    from config import WATCHLIST
    from backtest.engine import run_backtest

    print(f"\n{'='*60}")
    print(f"  Testing RELAXED_PULLBACK_MIN = {pullback_min}%")
    print(f"{'='*60}\n")

    result = run_backtest(
        watchlist=WATCHLIST,
        days=1200,
        save_csv=False,
        strategy_mode="RELAXED",
    )
    s  = result["summary"]
    pf = s.get("profit_factor", 0)
    pf_s = f"{pf:.2f}" if pf != float("inf") else "inf"

    print(f"\n  +--------------------------------------------------+")
    print(f"  |  RELAXED_PULLBACK_MIN = {pullback_min}%")
    print(f"  +--------------------------------------------------+")
    print(f"  |  Total Trades  : {s['total_trades']:<32}|")
    print(f"  |  Win Rate      : {s['win_rate_pct']:.2f}%{'':<29}|")
    print(f"  |  Profit Factor : {pf_s:<32}|")
    print(f"  |  Max Drawdown  : {s['max_drawdown_pct']:.2f}%{'':<29}|")
    print(f"  |  Total Return  : {s['total_return_pct']:+.2f}%{'':<29}|")
    print(f"  +--------------------------------------------------+")

    n = s["total_trades"]
    if TARGET_LOW <= n <= TARGET_HIGH:
        print(f"  [TARGET HIT] {n} trades is within {TARGET_LOW}-{TARGET_HIGH}.")
    elif n < TARGET_LOW:
        print(f"  [UNDER] {n} < {TARGET_LOW}")
    else:
        print(f"  [OVER]  {n} > {TARGET_HIGH}")

    return n, s


if __name__ == "__main__":
    # Test 3.5% — midpoint between 3.0 (284 trades) and 4.0 (163 trades)
    n, s = run_and_report(pullback_min=3.5)

    print("\n\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  RELAXED_PULLBACK_MIN   = 3.5%")
    print(f"  RELAXED_PULLBACK_MAX   = 8.0%  (unchanged)")
    print(f"  RELAXED_ADX_MIN        = 15.0  (unchanged)")
    print(f"  RELAXED_MIN_AVG_VOLUME = 200,000  (unchanged)")
    print(f"  RSI range              = 38-65  (unchanged)")
    print(f"  Total Trades  : {s['total_trades']}")
    print(f"  Win Rate      : {s['win_rate_pct']:.2f}%")
    pf = s.get("profit_factor", 0)
    print(f"  Profit Factor : {pf:.2f}" if pf != float('inf') else f"  Profit Factor : inf")
    print(f"  Max Drawdown  : {s['max_drawdown_pct']:.2f}%")
    print(f"  Total Return  : {s['total_return_pct']:+.2f}%")
    print("=" * 60)

    if TARGET_LOW <= n <= TARGET_HIGH:
        print(f"\n  [SUCCESS] Apply RELAXED_PULLBACK_MIN = 3.5 to config.py")
    elif n > TARGET_HIGH:
        print(f"\n  [HINT] Still over target. Try 3.7 or 3.8.")
    else:
        print(f"\n  [HINT] Under target. Try 3.3.")
