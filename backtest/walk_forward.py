# backtest/walk_forward.py
"""Strict walk-forward validation over the portfolio engine.

Splits each symbol's enriched history into contiguous, non-overlapping
segments.  Segment 0 is in-sample; the rest are out-of-sample.  The strategy
is declared robust only if every out-of-sample segment's profit factor stays
within ``OOS_MIN_PF_RATIO`` of the in-sample profit factor.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

import config as _cfg
from config import (
    WATCHLIST, INITIAL_CAPITAL, STRATEGY_MODE, MAX_OPEN_POSITIONS, POSITION_RISK_PCT,
)
from broker.zerodha_api import get_ohlcv_free
from strategy.indicators import enrich_with_indicators
from backtest.portfolio_engine import simulate
from backtest.run_portfolio import fetch_benchmark, build_regime_map
from backtest import metrics as metrics_mod

N_SEGMENTS = 3
OOS_MIN_PF_RATIO = 0.6


def split_indices(total: int, n_segments: int = N_SEGMENTS) -> list[tuple[int, int]]:
    """Contiguous, non-overlapping ``(start, end)`` row ranges covering ``total`` rows."""
    size = total // n_segments
    bounds = []
    for i in range(n_segments):
        start = i * size
        end = total if i == n_segments - 1 else (i + 1) * size
        bounds.append((start, end))
    return bounds


def evaluate_segments(in_sample_pf: float, oos_pfs: list[float],
                      min_ratio: float = OOS_MIN_PF_RATIO) -> dict:
    """Pass/fail verdict: each OOS profit factor must be >= min_ratio * in-sample PF."""
    floor = in_sample_pf * min_ratio
    failed = [i for i, pf in enumerate(oos_pfs) if pf < floor]
    return {"passed": len(failed) == 0, "floor": round(floor, 2),
            "failed_segments": failed}


def _segment_pf(data_slice: dict, entry_decision=None, exit_decision=None,
                warmup: int = 0, nifty_df: pd.DataFrame | None = None,
                regime_ok: dict | None = None) -> float:
    """Profit factor of one segment.

    ``warmup`` defaults to 0 because the data is already enriched (indicators
    warmed on the full history) before slicing; rows whose indicators are still
    NaN simply produce no entry signal, so no per-slice warm-up gate is needed.

    ``nifty_df`` / ``regime_ok`` thread the Phase 2 benchmark inputs so the
    out-of-sample verdict tests the same variant the full backtest ran.  The
    engine slices the benchmark to each signal date, so passing full-history
    benchmark data introduces no look-ahead.
    """
    sim = simulate(data_slice, start_capital=INITIAL_CAPITAL, strategy_mode=STRATEGY_MODE,
                   max_positions=MAX_OPEN_POSITIONS, risk_pct=POSITION_RISK_PCT,
                   warmup=warmup, entry_decision=entry_decision, exit_decision=exit_decision,
                   nifty_df=nifty_df, regime_ok=regime_ok)
    m = metrics_mod.compute_metrics(sim["trade_log"], sim["equity_curve"],
                                    sim["positions_count"], INITIAL_CAPITAL)
    pf = m["profit_factor"]
    return 999.0 if pf == float("inf") else pf


def run(watchlist: list[str] | None = None, days: int = 1200,
        loader=get_ohlcv_free, benchmark_loader=fetch_benchmark) -> dict:
    """Run the full walk-forward and print per-segment profit factors + verdict."""
    watchlist = watchlist if watchlist is not None else WATCHLIST
    enriched: dict[str, pd.DataFrame] = {}
    for sym in watchlist:
        try:
            df = loader(sym, days)
        except Exception:                              # noqa: BLE001
            continue
        if df is None or len(df) < 250:
            continue
        enriched[sym] = enrich_with_indicators(df)

    if not enriched:
        print("  [!] No data loaded for walk-forward.")
        return {"passed": False, "segment_pfs": []}

    # Phase 2 benchmark inputs (fetched only when a hypothesis flag needs them).
    benchmark = None
    regime_map = None
    if _cfg.REGIME_FILTER_ENABLED or _cfg.RS_FILTER_ENABLED:
        benchmark = benchmark_loader(days) if benchmark_loader else None
        if benchmark is not None and _cfg.REGIME_FILTER_ENABLED:
            regime_map = build_regime_map(benchmark)

    min_len = min(len(df) for df in enriched.values())
    bounds = split_indices(min_len, N_SEGMENTS)

    segment_pfs = []
    for seg_i, (start, end) in enumerate(bounds):
        data_slice = {s: df.iloc[start:end] for s, df in enriched.items()}
        pf = _segment_pf(data_slice,
                         nifty_df=benchmark if _cfg.RS_FILTER_ENABLED else None,
                         regime_ok=regime_map)
        segment_pfs.append(pf)
        label = "IN-SAMPLE" if seg_i == 0 else f"OOS #{seg_i}"
        print(f"  Segment {seg_i} [{label}] rows {start}:{end} -> profit factor {pf:.2f}")
        if (end - start) < 250:
            print(f"    [!] Segment {seg_i} has only {end - start} rows — too few bars; "
                  f"this segment's verdict may be unreliable.")

    verdict = evaluate_segments(segment_pfs[0], segment_pfs[1:])
    print("\n  " + ("[PASS] Strategy holds out-of-sample." if verdict["passed"]
                    else f"[FAIL] OOS degradation in segments {verdict['failed_segments']} "
                         f"(floor PF {verdict['floor']})."))
    return {"passed": verdict["passed"], "segment_pfs": segment_pfs}


if __name__ == "__main__":
    run()
