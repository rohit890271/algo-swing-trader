"""Main entry-point for the swing trading backtest system.

Usage::

    python main.py

Loads daily OHLCV for every symbol in ``config.WATCHLIST`` from Yahoo Finance,
runs the portfolio-level backtest, and prints the baseline tear-sheet.
"""

from backtest.run_portfolio import main

if __name__ == "__main__":
    main()
