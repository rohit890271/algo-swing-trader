"""
Backtesting engine for the swing trading strategy.

Fetches historical OHLCV data via Yahoo Finance (``get_ohlcv_free``),
iterates day-by-day from bar 50 onwards, and uses
:func:`check_entry_signal` / :func:`check_exit_signal` to simulate
paper trades.  Produces a trade log CSV and prints a performance
summary.

Dependencies: pandas, numpy, yfinance
"""

from __future__ import annotations

import sys
import os

# Ensure the project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd

from config import (
    INITIAL_CAPITAL,
    WATCHLIST,
    PAPER_TRADE,
    MAX_HOLD_DAYS,
    POSITION_RISK_PCT,
    MIN_AVG_VOLUME,
)
from broker.zerodha_api import get_ohlcv_free
from strategy.signals import check_entry_signal, check_exit_signal
from strategy.risk import calculate_atr_stop_loss, calculate_target, position_size


# ──────────────────────────────────────────────
# Trade record helper
# ──────────────────────────────────────────────

def _empty_trade_log() -> pd.DataFrame:
    """Return an empty DataFrame with the trade-log schema.

    Returns:
        A ``pandas.DataFrame`` with the correct column names and dtypes
        but zero rows.
    """
    return pd.DataFrame(columns=[
        "symbol", "entry_date", "exit_date",
        "entry_price", "exit_price", "pnl_pct", "exit_reason",
    ])


# ──────────────────────────────────────────────
# Core backtest loop for a single symbol
# ──────────────────────────────────────────────

def _backtest_symbol(symbol: str, df: pd.DataFrame, nifty_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Run a day-by-day backtest on one symbol.

    Starts from bar index 200 (so all indicators have warmed up) and
    scans forward one bar at a time.  When not in a trade it calls
    :func:`check_entry_signal`; when in a trade it calls
    :func:`check_exit_signal`.

    Args:
        symbol:   NSE ticker name.
        df:       OHLCV DataFrame (>= 250 rows) with a DatetimeIndex.
        nifty_df: Optional Nifty 50 benchmark DataFrame for RS calc.

    Returns:
        A ``pandas.DataFrame`` of completed trades for this symbol.
    """
    trades = []
    in_trade = False
    entry_price = 0.0
    entry_date = None
    stop_loss = 0.0
    target = 0.0
    partial_taken = False       # tracks whether 50% partial exit done
    position_pct = 1.0          # 1.0 = full, 0.5 = half remaining

    # Pre-calculate all indicators to vectorize O(N^2) calculations
    if "ema_20" not in df.columns:
        from strategy.indicators import enrich_with_indicators
        df = enrich_with_indicators(df)

    start_bar = 50  # skip first 50 bars for short-term indicator warm-up
    for i in range(start_bar, len(df)):
        # Slice up to and including the current bar
        window = df.iloc[: i + 1]
        current_bar = df.iloc[i]
        current_date = df.index[i]

        if not in_trade:
            # -- Check for an entry -----------
            nifty_window = None
            if nifty_df is not None:
                nifty_window = nifty_df.loc[nifty_df.index <= current_date]
            result = check_entry_signal(window, nifty_df=nifty_window)
            if result["signal"]:
                entry_price = current_bar["close"]
                entry_date = current_date

                # ATR-based stop loss (1.5x ATR, clamped 1.5%-4%)
                atr_val = current_bar.get("atr", 0.0)
                if atr_val == 0.0:
                    from strategy.indicators import atr as compute_atr_series
                    atr_val = compute_atr_series(window).iloc[-1]
                stop_loss = calculate_atr_stop_loss(entry_price, atr_value=atr_val)

                target = calculate_target(entry_price, target_pct=0.08)
                in_trade = True
                partial_taken = False
                position_pct = 1.0

                sl_pct = ((entry_price - stop_loss) / entry_price) * 100
                if PAPER_TRADE:
                    print(
                        f"  [ENTRY] [{symbol}] on {str(current_date)[:10]} "
                        f"@ {entry_price:,.2f}  |  SL {stop_loss:,.2f} ({sl_pct:.1f}%)  "
                        f"|  TGT {target:,.2f}"
                    )
        else:
            # -- Check for an exit ------------
            reason = check_exit_signal(
                window,
                entry_price=entry_price,
                entry_date=entry_date,
                stop_loss=stop_loss,
                target=target,
                max_hold_days=MAX_HOLD_DAYS,
                partial_taken=partial_taken,
            )

            if reason == "PARTIAL_EXIT_5PCT":
                # Book 50% of the position at current price
                exit_price = current_bar["close"]
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0

                trades.append({
                    "symbol": symbol,
                    "entry_date": entry_date,
                    "exit_date": current_date,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "exit_reason": "PARTIAL_EXIT_50%",
                })

                if PAPER_TRADE:
                    print(
                        f"  [PARTIAL] [{symbol}] 50% EXIT on {str(current_date)[:10]} "
                        f"@ {exit_price:,.2f}  |  P&L {pnl_pct:+.2f}%  "
                        f"|  Remaining 50% trailing..."
                    )

                partial_taken = True
                position_pct = 0.5
                # Tighten stop to entry (breakeven) for remaining half
                stop_loss = entry_price

            elif reason != "HOLD":
                # Full exit of remaining position
                exit_price = current_bar["close"]
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
                exit_label = reason if position_pct == 1.0 else f"{reason}_RUNNER"

                trades.append({
                    "symbol": symbol,
                    "entry_date": entry_date,
                    "exit_date": current_date,
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "exit_reason": exit_label,
                })

                if PAPER_TRADE:
                    pct_label = "100%" if position_pct == 1.0 else "50%"
                    status_lbl = "[WIN]" if pnl_pct > 0 else "[LOSS]"
                    print(
                        f"  {status_lbl} [{symbol}] {pct_label} EXIT on {str(current_date)[:10]} "
                        f"@ {exit_price:,.2f}  |  P&L {pnl_pct:+.2f}%  "
                        f"|  Reason: {exit_label}"
                    )

                in_trade = False

    if not trades:
        return _empty_trade_log()
    return pd.DataFrame(trades)


# ──────────────────────────────────────────────
# Performance summary
# ──────────────────────────────────────────────

def _compute_summary(trade_log: pd.DataFrame, capital: float) -> dict:
    """Compute aggregate performance metrics from a trade log.

    Args:
        trade_log: DataFrame of completed trades (needs ``pnl_pct``).
        capital:   Starting capital (used for total return calc).

    Returns:
        A dict of summary statistics.
    """
    if trade_log.empty:
        return {
            "total_trades": 0,
            "winners": 0,
            "losers": 0,
            "win_rate_pct": 0.0,
            "avg_profit_pct": 0.0,
            "avg_loss_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "total_return_pct": 0.0,
        }

    total = len(trade_log)
    winners = trade_log[trade_log["pnl_pct"] > 0]
    losers = trade_log[trade_log["pnl_pct"] <= 0]

    win_rate = (len(winners) / total) * 100.0 if total else 0.0
    avg_profit = winners["pnl_pct"].mean() if len(winners) else 0.0
    avg_loss = losers["pnl_pct"].mean() if len(losers) else 0.0

    # Approximate max drawdown from cumulative P&L
    cumulative = (1 + trade_log["pnl_pct"] / 100.0).cumprod()
    running_max = cumulative.cummax()
    drawdown = ((cumulative - running_max) / running_max) * 100.0
    max_dd = abs(drawdown.min()) if len(drawdown) else 0.0

    total_return = (cumulative.iloc[-1] - 1) * 100.0 if len(cumulative) else 0.0

    return {
        "total_trades": total,
        "winners": len(winners),
        "losers": len(losers),
        "win_rate_pct": round(win_rate, 2),
        "avg_profit_pct": round(avg_profit, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "total_return_pct": round(total_return, 2),
    }


def _print_summary(summary: dict) -> None:
    """Pretty-print the performance summary to stdout.

    Args:
        summary: Dict returned by :func:`_compute_summary`.
    """
    print("\n" + "=" * 55)
    print("  [BACKTEST PERFORMANCE SUMMARY]")
    print("=" * 55)
    print(f"  Total Trades      : {summary['total_trades']}")
    print(f"  Winners           : {summary['winners']}")
    print(f"  Losers            : {summary['losers']}")
    print(f"  Win Rate          : {summary['win_rate_pct']:.2f}%")
    print(f"  Avg Profit (win)  : {summary['avg_profit_pct']:+.2f}%")
    print(f"  Avg Loss (loss)   : {summary['avg_loss_pct']:+.2f}%")
    print(f"  Max Drawdown      : {summary['max_drawdown_pct']:.2f}%")
    print(f"  Total Return      : {summary['total_return_pct']:+.2f}%")
    print("=" * 55)


# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────

def run_backtest(
    watchlist: list | None = None,
    days: int = 1200,
    save_csv: bool = True,
    csv_path: str = "trades_log.csv",
) -> dict:
    """Run the full backtest across every symbol in the watchlist.

    For each symbol:
      1. Fetch *days* of daily OHLCV data via Yahoo Finance.
      2. Iterate day-by-day from bar 50 onwards.
      3. Call ``check_entry_signal()`` / ``check_exit_signal()``.
      4. Record every trade (paper mode — no real orders).

    Args:
        watchlist: List of NSE symbols.  Defaults to ``config.WATCHLIST``.
        days:      Number of calendar days of history to fetch.
        save_csv:  Whether to save the trade log to a CSV file.
        csv_path:  Path for the output CSV (default ``trades_log.csv``).

    Returns:
        A dict with keys:

        * ``"trade_log"``  – ``pd.DataFrame`` of all trades.
        * ``"summary"``    – ``dict`` of aggregate metrics.
    """
    if watchlist is None:
        watchlist = WATCHLIST

    print("=" * 55)
    print("  [SWING TRADING BACKTEST ENGINE]")
    print(f"  Mode : {'PAPER TRADE' if PAPER_TRADE else 'LIVE (caution!)'}")
    print(f"  Symbols : {len(watchlist)} stocks")
    print(f"  History : {days} days")
    print("=" * 55)

    # -- Fetch Nifty 50 benchmark once --------
    print("\n  Fetching Nifty 50 benchmark (^NSEI)...")
    try:
        import yfinance as yf
        nifty_raw = yf.download("^NSEI", period=f"{days}d", interval="1d", auto_adjust=True)
        if isinstance(nifty_raw.columns, pd.MultiIndex):
            nifty_raw.columns = nifty_raw.columns.get_level_values(0)
        nifty_df = nifty_raw.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })[["open", "high", "low", "close", "volume"]].dropna()
        print(f"  [OK] Nifty 50 benchmark: {len(nifty_df)} bars loaded.")
    except Exception as e:
        print(f"  [!] Could not fetch Nifty 50 benchmark: {e}")
        print("       RS filter will be skipped.")
        nifty_df = None

    all_trades = []

    for symbol in watchlist:
        print(f"\n{'-' * 45}")
        print(f"  Scanning: {symbol}")
        print(f"{'-' * 45}")

        try:
            df = get_ohlcv_free(symbol, days=days)
        except Exception as e:
            print(f"  [!] Failed to fetch data for {symbol}: {e}")
            continue

        if len(df) < 250:
            print(f"  [!] Only {len(df)} bars for {symbol}, need >= 250. Skipping.")
            continue

        # ── Volume liquidity filter ──────────
        avg_vol_20 = df["volume"].tail(20).mean()
        if avg_vol_20 < MIN_AVG_VOLUME:
            print(
                f"  [!] {symbol} avg 20-day volume = {avg_vol_20:,.0f} "
                f"< {MIN_AVG_VOLUME:,}. Skipping."
            )
            continue

        symbol_trades = _backtest_symbol(symbol, df, nifty_df=nifty_df)

        if symbol_trades.empty:
            print(f"  [-] No trades generated for {symbol}.")
        else:
            all_trades.append(symbol_trades)

    # ── Combine results ──────────────────────
    if all_trades:
        trade_log = pd.concat(all_trades, ignore_index=True)
    else:
        trade_log = _empty_trade_log()

    summary = _compute_summary(trade_log, INITIAL_CAPITAL)
    _print_summary(summary)

    # ── Save CSV ─────────────────────────────
    if save_csv and not trade_log.empty:
        trade_log.to_csv(csv_path, index=False)
        print(f"\n  [SAVED] Trade log saved to: {csv_path}")
    elif save_csv:
        print("\n  [-] No trades to save.")

    return {
        "trade_log": trade_log,
        "summary": summary,
    }


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    run_backtest()
