"""Thin runner: load the universe, enrich, simulate, report.

This is the only backtest module that performs network I/O.  The data loader
is injectable so tests can run without Yahoo Finance.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

import config as _cfg
from config import (
    WATCHLIST, INITIAL_CAPITAL, STRATEGY_MODE, MAX_OPEN_POSITIONS,
    POSITION_RISK_PCT, STRICT_MIN_AVG_VOLUME, RELAXED_MIN_AVG_VOLUME,
    SURVIVORSHIP_HAIRCUT_PCT, REGIME_EMA_PERIOD,
)
from broker.zerodha_api import get_ohlcv_free
from strategy.indicators import enrich_with_indicators, ema
from backtest.portfolio_engine import simulate
from backtest import metrics as metrics_mod

MIN_BARS = 250


def fetch_benchmark(days: int = 1200) -> pd.DataFrame | None:
    """Fetch the Nifty 50 index (^NSEI) OHLCV from Yahoo Finance.

    Kept separate from ``get_ohlcv_free`` because that helper appends ``.NS``
    to plain symbols, which would mangle the index ticker.
    """
    try:
        import yfinance as yf
        raw = yf.download("^NSEI", period=f"{days}d", interval="1d",
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = raw.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
        return df
    except Exception as exc:                           # noqa: BLE001 - network resilience
        print(f"  [!] Could not fetch Nifty benchmark: {exc}")
        return None


def build_regime_map(benchmark: pd.DataFrame,
                     ema_period: int = REGIME_EMA_PERIOD) -> dict:
    """Per-date bull/bear map: True where the index close > its ``ema_period`` EMA.

    The EMA is causal, so slicing this map by date introduces no look-ahead.
    """
    bench_ema = ema(benchmark["close"], ema_period)
    ok = benchmark["close"] > bench_ema
    return {date: bool(val) for date, val in ok.items()}


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
        exit_decision=None, benchmark_loader=fetch_benchmark) -> dict:
    """Run a portfolio backtest and return metrics + trade log.

    The Nifty benchmark is fetched only when a Phase 2 hypothesis flag
    (``REGIME_FILTER_ENABLED`` / ``RS_FILTER_ENABLED``) needs it, so the
    default flags-off path performs no extra network I/O.
    """
    watchlist = watchlist if watchlist is not None else WATCHLIST
    data = load_universe(watchlist, days, loader, strategy_mode)

    benchmark = None
    regime_map = None
    if _cfg.REGIME_FILTER_ENABLED or _cfg.RS_FILTER_ENABLED:
        benchmark = benchmark_loader(days) if benchmark_loader else None
        if benchmark is not None and _cfg.REGIME_FILTER_ENABLED:
            regime_map = build_regime_map(benchmark)

    sim = simulate(data, start_capital=INITIAL_CAPITAL, strategy_mode=strategy_mode,
                   max_positions=MAX_OPEN_POSITIONS, risk_pct=POSITION_RISK_PCT,
                   entry_decision=entry_decision, exit_decision=exit_decision,
                   nifty_df=benchmark if _cfg.RS_FILTER_ENABLED else None,
                   regime_ok=regime_map)

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
