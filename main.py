"""
Main entry-point for the swing trading backtest system.

Usage::

    python main.py

Fetches live OHLCV data from Yahoo Finance for every symbol in
``config.WATCHLIST``, runs the day-by-day backtest, and saves
the trade log to ``trades_log.csv``.
"""

from backtest.engine import run_backtest


def main() -> None:
    """Run the full swing-trade backtest and print results."""
    result = run_backtest()

    trade_log = result["trade_log"]
    if not trade_log.empty:
        print("\n[Detailed Trade Log]")
        print(trade_log.to_string(index=False))
    else:
        print("\n[!] No trades were generated across all symbols.")

    print("\n[DONE]")


if __name__ == "__main__":
    main()
