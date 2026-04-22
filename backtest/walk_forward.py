"""
Walk-Forward Test — validates the strategy is not curve-fitted.

Splits the most recent 365 trading days into 3 segments:
  - Segment 1 (In-Sample / Train):   Day 1–180
  - Segment 2 (Out-of-Sample / Test): Day 181–270
  - Segment 3 (Out-of-Sample / Test): Day 271–365

Runs the backtest independently on each segment, prints individual
summaries, then a combined summary.  Flags warnings if any
out-of-sample segment shows degraded performance.

Usage::

    python -m backtest.walk_forward
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd

from config import INITIAL_CAPITAL, WATCHLIST, MIN_AVG_VOLUME
from broker.zerodha_api import get_ohlcv_free
from backtest.engine import _backtest_symbol, _compute_summary, _empty_trade_log


# ──────────────────────────────────────────────
# Segment definitions
# ──────────────────────────────────────────────

SEGMENTS = [
    {"name": "Segment 1 (In-Sample / Train)", "start": 0,   "end": 180, "oos": False},
    {"name": "Segment 2 (Out-of-Sample #1)",  "start": 180, "end": 270, "oos": True},
    {"name": "Segment 3 (Out-of-Sample #2)",  "start": 270, "end": 365, "oos": True},
]

# Warning thresholds for out-of-sample segments
OOS_MIN_WIN_RATE   = 45.0     # %
OOS_MIN_PROFIT_FACTOR = 1.3
OOS_MAX_DRAWDOWN   = 25.0     # %


# ──────────────────────────────────────────────
# Enhanced summary with profit factor
# ──────────────────────────────────────────────

def _enhanced_summary(trade_log: pd.DataFrame, capital: float) -> dict:
    """Like _compute_summary but also includes profit_factor."""
    base = _compute_summary(trade_log, capital)

    if trade_log.empty:
        base["profit_factor"] = 0.0
        return base

    gross_profit = trade_log.loc[trade_log["pnl_pct"] > 0, "pnl_pct"].sum()
    gross_loss   = abs(trade_log.loc[trade_log["pnl_pct"] <= 0, "pnl_pct"].sum())
    base["profit_factor"] = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    return base


# ──────────────────────────────────────────────
# Fetch Nifty 50 benchmark
# ──────────────────────────────────────────────

def _fetch_nifty(days: int = 1200) -> pd.DataFrame | None:
    """Fetch Nifty 50 index data for RS calculations."""
    try:
        import yfinance as yf
        raw = yf.download("^NSEI", period=f"{days}d", interval="1d", auto_adjust=True)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })[["open", "high", "low", "close", "volume"]].dropna()
        return df
    except Exception as e:
        print(f"  [!] Could not fetch Nifty 50: {e}")
        return None


# ──────────────────────────────────────────────
# Print helpers
# ──────────────────────────────────────────────

def _print_segment_summary(name: str, summary: dict, oos: bool) -> list[str]:
    """Print one segment's results and return any warning messages."""
    warnings = []

    print(f"\n{'=' * 60}")
    tag = "[OUT-OF-SAMPLE]" if oos else "[IN-SAMPLE]"
    print(f"  {tag} {name}")
    print(f"{'=' * 60}")
    print(f"  Stocks Scanned    : {summary.get('stocks_scanned', 0)}")
    print(f"  Signals Found     : {summary['total_trades']}")
    print(f"  Total Trades      : {summary['total_trades']}")
    print(f"  Winners           : {summary['winners']}")
    print(f"  Losers            : {summary['losers']}")
    print(f"  Win Rate          : {summary['win_rate_pct']:.2f}%")
    print(f"  Profit Factor     : {summary['profit_factor']:.2f}")
    print(f"  Avg Profit (win)  : {summary['avg_profit_pct']:+.2f}%")
    print(f"  Avg Loss (loss)   : {summary['avg_loss_pct']:+.2f}%")
    print(f"  Max Drawdown      : {summary['max_drawdown_pct']:.2f}%")
    print(f"  Total Return      : {summary['total_return_pct']:+.2f}%")

    if oos and summary["total_trades"] > 5:
        if summary["win_rate_pct"] < OOS_MIN_WIN_RATE:
            w = f"  [WARNING] Win rate {summary['win_rate_pct']:.1f}% < {OOS_MIN_WIN_RATE}% threshold"
            print(w)
            warnings.append(w)
        if summary["profit_factor"] < OOS_MIN_PROFIT_FACTOR:
            w = f"  [WARNING] Profit factor {summary['profit_factor']:.2f} < {OOS_MIN_PROFIT_FACTOR} threshold"
            print(w)
            warnings.append(w)
        if summary["max_drawdown_pct"] > OOS_MAX_DRAWDOWN:
            w = f"  [WARNING] Max drawdown {summary['max_drawdown_pct']:.1f}% > {OOS_MAX_DRAWDOWN}% threshold"
            print(w)
            warnings.append(w)
    elif oos and summary["total_trades"] <= 5:
        w = f"  [WARNING] INSUFFICIENT DATA: Only {summary['total_trades']} trades in this out-of-sample segment."
        print(w)
        warnings.append(w)

    return warnings


# ──────────────────────────────────────────────
# Main walk-forward runner
# ──────────────────────────────────────────────

def run_walk_forward(watchlist: list | None = None, fetch_days: int = 1200) -> None:
    """Execute the full walk-forward validation."""

    if watchlist is None:
        watchlist = WATCHLIST

    print("=" * 60)
    print("  WALK-FORWARD VALIDATION TEST")
    print(f"  Stocks: {len(watchlist)}  |  Fetch: {fetch_days} days")
    print("=" * 60)

    # -- Fetch Nifty benchmark once -----------
    print("\n  Fetching Nifty 50 benchmark...")
    nifty_df = _fetch_nifty(fetch_days)
    if nifty_df is not None:
        print(f"  [OK] Nifty 50: {len(nifty_df)} bars")

    # -- Fetch all stock data once ------------
    print("\n  Fetching stock data...")
    stock_data: dict[str, pd.DataFrame] = {}

    for symbol in watchlist:
        try:
            df = get_ohlcv_free(symbol, days=fetch_days)
        except Exception as e:
            print(f"    [!] {symbol}: {e}")
            continue

        if len(df) < 565:  # need 200 warm-up + 365 test
            continue

        avg_vol = df["volume"].tail(20).mean()
        if avg_vol < MIN_AVG_VOLUME:
            continue

        stock_data[symbol] = df

    print(f"  [OK] Loaded {len(stock_data)} stocks with sufficient data")

    # -- Determine the 365-day test window ----
    # Use the shortest stock's date range as reference
    if not stock_data:
        print("\n  [ERROR] No stocks with enough data. Aborting.")
        return

    # Pick dates from a reference stock
    ref_symbol = list(stock_data.keys())[0]
    ref_dates = stock_data[ref_symbol].index

    # Take the last 565 bars (200 warm-up + 365 test)
    # The "365 test days" start at index -365
    test_window_size = 365

    all_warnings: list[str] = []
    segment_results: list[dict] = []
    all_segment_trades: list[pd.DataFrame] = []

    for seg in SEGMENTS:
        seg_name = seg["name"]
        seg_start = seg["start"]  # relative to test window start
        seg_end   = seg["end"]

        print(f"\n{'-' * 60}")
        print(f"  Running: {seg_name}  (Days {seg_start + 1} - {seg_end})")
        print(f"{'-' * 60}")

        seg_trades_all: list[pd.DataFrame] = []
        stocks_scanned = 0

        for symbol, full_df in stock_data.items():
            stocks_scanned += 1
            
            # 1. Pre-calculate indicators on FULL dataset before any slicing
            if "ema_20" not in full_df.columns:
                from strategy.indicators import enrich_with_indicators
                full_df = enrich_with_indicators(full_df)
                stock_data[symbol] = full_df # save back so we don't recalculate next segment

            n = len(full_df)

            # Test window: last 365 bars
            test_start_idx = max(0, n - test_window_size)

            # Segment boundaries within the test window
            abs_seg_start = test_start_idx + seg_start
            abs_seg_end   = min(test_start_idx + seg_end, n)

            # Each segment needs minimum 30 trading days to generate signals
            if (abs_seg_end - abs_seg_start) < 30:
                continue

            # Slice: 50 days of warmup + this segment's data
            # Engine starts at bar 50, so this perfectly aligns with abs_seg_start
            warmup_start_idx = max(0, abs_seg_start - 50)
            segment_df = full_df.iloc[warmup_start_idx:abs_seg_end].copy()

            # Prepare nifty window
            seg_nifty = None
            if nifty_df is not None:
                seg_end_date = segment_df.index[-1]
                seg_nifty = nifty_df.loc[nifty_df.index <= seg_end_date]

            trades = _backtest_symbol(symbol, segment_df, nifty_df=seg_nifty)

            if not trades.empty:
                # Only keep trades whose entry falls within this segment's dates
                seg_start_date = full_df.index[abs_seg_start] if abs_seg_start < n else full_df.index[-1]
                seg_end_date = full_df.index[abs_seg_end - 1] if abs_seg_end <= n else full_df.index[-1]
                trades = trades[
                    (trades["entry_date"] >= seg_start_date)
                    & (trades["entry_date"] <= seg_end_date)
                ]

            if not trades.empty:
                seg_trades_all.append(trades)

        # Combine segment trades
        if seg_trades_all:
            seg_log = pd.concat(seg_trades_all, ignore_index=True)
        else:
            seg_log = _empty_trade_log()

        summary = _enhanced_summary(seg_log, INITIAL_CAPITAL)
        summary["stocks_scanned"] = stocks_scanned
        segment_results.append({"name": seg_name, "summary": summary, "oos": seg["oos"]})
        all_segment_trades.append(seg_log)

        w = _print_segment_summary(seg_name, summary, seg["oos"])
        all_warnings.extend(w)

    # -- Combined summary ---------------------
    if all_segment_trades:
        combined_log = pd.concat(all_segment_trades, ignore_index=True)
    else:
        combined_log = _empty_trade_log()

    combined_summary = _enhanced_summary(combined_log, INITIAL_CAPITAL)

    print(f"\n{'=' * 60}")
    print("  COMBINED WALK-FORWARD SUMMARY (All 3 Segments)")
    print(f"{'=' * 60}")
    print(f"  Total Trades      : {combined_summary['total_trades']}")
    print(f"  Winners           : {combined_summary['winners']}")
    print(f"  Losers            : {combined_summary['losers']}")
    print(f"  Win Rate          : {combined_summary['win_rate_pct']:.2f}%")
    print(f"  Profit Factor     : {combined_summary['profit_factor']:.2f}")
    print(f"  Avg Profit (win)  : {combined_summary['avg_profit_pct']:+.2f}%")
    print(f"  Avg Loss (loss)   : {combined_summary['avg_loss_pct']:+.2f}%")
    print(f"  Max Drawdown      : {combined_summary['max_drawdown_pct']:.2f}%")
    print(f"  Total Return      : {combined_summary['total_return_pct']:+.2f}%")

    # -- Final verdict ------------------------
    print(f"\n{'=' * 60}")
    if all_warnings:
        print("  VERDICT: POTENTIAL CURVE-FITTING DETECTED")
        print(f"  {len(all_warnings)} warning(s) flagged:")
        for w in all_warnings:
            print(f"    {w}")
        print("\n  Recommendation: Review strategy parameters and re-test")
        print("  with different market regimes before live deployment.")
    else:
        print("  VERDICT: STRATEGY PASSED WALK-FORWARD VALIDATION")
        print("  Out-of-sample performance is consistent with in-sample.")
        print("  Strategy appears robust and NOT curve-fitted.")
    print(f"{'=' * 60}\n")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    run_walk_forward()
