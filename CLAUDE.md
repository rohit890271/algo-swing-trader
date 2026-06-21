# CLAUDE.md

Guidance for working in this repo. This is an **algorithmic swing-trading system** for
Indian equities (NSE) written in Python. It scans Nifty 100 + Midcap 50 for pullback-in-uptrend
setups, backtests them on historical data, and runs a daily paper-trading scan. **No real orders
are placed** — the broker layer is a stub and all data comes from Yahoo Finance.

## Commands

```bash
# Setup (Windows, Python 3.13)
python -m venv .venv && .\.venv\Scripts\activate
pip install ta_lib-0.6.8-cp313-cp313-win_amd64.whl   # bundled wheel, TA-Lib is a hard dep
pip install -r requirements.txt

# Historical backtest: portfolio-level, shared capital, cost-aware -> tear-sheet
python main.py

# Compare STRICT vs RELAXED side-by-side (legacy per-symbol engine)
python compare_modes.py

# Walk-forward (strict non-overlapping 3-segment OOS check over the portfolio engine)
python -m backtest.walk_forward

# Run the full test suite
.venv/Scripts/python.exe -m pytest -q

# Daily paper-trade scan: runs once immediately, then schedules 09:20 IST daily
python paper_trade/paper_engine.py

# Analyze a saved trade log CSV
python analyze_results.py
```

There is a pytest suite under `tests/` (no linter config or CI). Run it with
`.venv/Scripts/python.exe -m pytest -q`. Beyond that, verification is manual: run a backtest
and read the printed tear-sheet.

## Architecture

Data flow: `yfinance OHLCV -> enrich_with_indicators -> check_entry_signal/check_exit_signal -> risk sizing -> trade log`

- **config.py** — single source of truth for every tunable (capital, risk %, indicator periods,
  STRICT/RELAXED thresholds, watchlists, Kite creds). Every module imports constants from here.
- **strategy/indicators.py** — TA-Lib wrappers (EMA 20/50/200, RSI, ADX, ATR) plus rolling highs,
  1-week return, 5-day volume average. `enrich_with_indicators(df)` attaches all of them at once.
- **strategy/signals.py** — the real strategy lives in `check_entry_signal()` (a 9-condition
  pullback screener evaluating the **latest bar**) and `check_exit_signal()` (priority-ordered exit:
  target → stop → partial-5% → time → momentum-fade → RSI-overbought → bearish-reversal → hold).
- **strategy/risk.py** — fixed-fractional position sizing, ATR/percentage stops, trailing stops,
  target prices, portfolio constraints.
- **broker/zerodha_api.py** — `ZerodhaAPI` is a fully-stubbed Kite Connect wrapper (no live calls).
  The function actually used everywhere is `get_ohlcv_free(symbol, days)`, which pulls free NSE data
  from Yahoo Finance (auto-appends `.NS`).
- **backtest/engine.py** — `run_backtest()` loops each symbol day-by-day from bar 50, calling the
  same entry/exit functions the paper engine uses. `_compute_summary()` builds the metrics. No
  longer wired into `main.py` (kept for reference); superseded by the portfolio engine below.
- **backtest/portfolio_engine.py** — pure date-driven portfolio simulator (shared capital,
  position cap, next-open fills, intrabar stop/target, costs). Injectable entry/exit fns.
- **backtest/costs.py / metrics.py** — trading-cost model and equity-curve metrics + tear-sheet.
- **backtest/run_portfolio.py** — thin runner (network I/O lives here); `main.py` calls it.
- **backtest/walk_forward.py** — strict non-overlapping 3-segment split over the portfolio engine;
  flags out-of-sample profit-factor degradation vs. `OOS_MIN_PF_RATIO`.
- **paper_trade/paper_engine.py** — daily live scan. Loads open positions from
  `paper_trades/open_positions.json`, checks exits, scans the full watchlist for entries, writes
  `paper_trades/daily_scan_log.csv` (one row per stock per scan with pass/fail reason) and
  `paper_trades/closed_trades.csv`.

## Conventions

- **OHLCV schema is always lowercase**: `open, high, low, close, volume`, with a `DatetimeIndex`.
  yfinance MultiIndex columns are flattened and renamed at the broker boundary — keep it that way.
- **Indicators are added as columns**, not recomputed inline. Call `enrich_with_indicators` once;
  the entry/exit functions assume `ema_20/50/200, rsi, adx, atr, high_10d, high_20d,
  return_1w_pct, vol_avg_5d` exist (they fall back to computing if missing).
- **STRICT vs RELAXED** is selected by `STRATEGY_MODE` in config and threaded through as a
  `strategy_mode` string argument. STRICT requires price > EMA-200; RELAXED drops that and widens
  RSI/pullback/ADX bands.
- Style: module docstrings, Google-style function docstrings with Args/Returns/Raises, section
  banners with `─` rules, type hints via `from __future__ import annotations`. Match this density.
- Console output uses `[PASS]/[FAIL]/[ENTRY]/[EXIT]` ASCII tags (no emoji — Windows console).
- New tunables go in **config.py**, never hard-coded at call sites.

## Known gotchas / open limitations

The original entry-signal duplication, stop-loss doc drift, mode-default mismatch, and the
"8 vs 9 conditions" docstring have been fixed. Remaining things to keep in mind:

- **`STRATEGY_MODE` is config-driven everywhere now.** `run_backtest`, `_backtest_symbol`,
  `walk_forward`, and the paper engine all default to `config.STRATEGY_MODE` (currently `RELAXED`).
  `compare_modes.py` still passes explicit modes to run both. Override per-call with the
  `strategy_mode` arg.
- **Stop-loss** uses `calculate_atr_stop_loss()` (1.5× ATR, clamped 1.5%–4%). The older
  `atr_stop_loss()` (2× ATR) and `build_trade_risk()` in risk.py are **not on the live path** —
  the `ATR_STOP_MULTIPLIER = 2.0` constant only feeds those unused helpers.
- **The backtest now models shared capital (portfolio-level).** `backtest/portfolio_engine.py`
  trades one capital account across the whole universe with a max concurrent position cap,
  next-open fills, and costs — it no longer pretends each symbol has its own unlimited capital.
- **Forward-test equity persists.** The paper engine now carries a running equity figure across
  daily runs (`load_portfolio_state`/`save_portfolio_state`/`apply_realized_pnl` in
  `paper_trade/paper_engine.py`), stored at `paper_trades/portfolio_state.json`. Sector limits
  (`MAX_SECTOR_POSITIONS`, `can_open_new_position`) are still defined but **not wired in** — no
  sector map. (Open item for pre-deployment.)
- **Survivorship bias**: the watchlist is *today's* index constituents applied to historical data,
  so backtest returns are optimistic. (Open item for pre-deployment.)
- Going live means replacing the stub bodies in `ZerodhaAPI` (`login`, `place_order`, …) and
  swapping the yfinance data source — currently nothing can place an order.

## Tests

`tests/` holds a pytest smoke suite covering the pure functions (risk sizing, stops, targets,
indicator schema, and entry/exit verdicts on synthetic data). Run with `python -m pytest -q`.
Network-dependent code (yfinance fetches, the scheduler) is intentionally not covered.
