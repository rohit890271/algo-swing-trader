"""Research round 2: push MAR toward the ~0.8 deployability bar.

Builds on the adopted H1 (regime) + H2 (trailing) base and tests two bounded,
pre-registered levers ONE AT A TIME against the walk-forward OOS guardrail:

  R-A  ATR-adaptive trailing distance   -- TRAILING_STOP_MODE="atr", mult in {2.0, 2.5, 3.0}
  R-B  Regime responsiveness            -- REGIME_EMA_PERIOD in {50, 100, 200(base)}

Discipline (from the Phase 2 plan): <=3 values per parameter, judge on OOS,
no tuning-to-target. A variant is only worth adopting if it PASSES the OOS
guardrail AND improves OOS profit factor / MAR over BASE_R2. If nothing does,
that is the honest answer and we stop.

Usage::

    python -m backtest.research_round2
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time

import config as _cfg
from config import WATCHLIST, INITIAL_CAPITAL, STRATEGY_MODE
from broker.zerodha_api import get_ohlcv_free
from backtest.run_portfolio import load_universe, fetch_benchmark, build_regime_map
from backtest.portfolio_engine import simulate
from backtest.walk_forward import (
    split_indices, evaluate_segments, _segment_stats, N_SEGMENTS,
)
from backtest import metrics as metrics_mod

# Every variant keeps H1+H2 on (the adopted base); only the swept attrs change.
# Each entry: (name, {config_attr: value, ...}).
VARIANTS = [
    ("BASE_R2", {}),                                                      # pct trail, regime 200
    ("ATR_2.0", {"TRAILING_STOP_MODE": "atr", "TRAILING_ATR_MULT": 2.0}),
    ("ATR_2.5", {"TRAILING_STOP_MODE": "atr", "TRAILING_ATR_MULT": 2.5}),
    ("ATR_3.0", {"TRAILING_STOP_MODE": "atr", "TRAILING_ATR_MULT": 3.0}),
    ("REGIME_50", {"REGIME_EMA_PERIOD": 50}),
    ("REGIME_100", {"REGIME_EMA_PERIOD": 100}),
]

# Attributes any variant may override (saved/restored around each run).
_MUTABLE = ("TRAILING_STOP_MODE", "TRAILING_ATR_MULT", "REGIME_EMA_PERIOD",
            "REGIME_FILTER_ENABLED", "TRAILING_EXIT_ENABLED", "RS_FILTER_ENABLED")


def _run_variant(name: str, overrides: dict, data: dict, benchmark) -> dict:
    saved = {attr: getattr(_cfg, attr) for attr in _MUTABLE}
    for attr, value in overrides.items():
        setattr(_cfg, attr, value)
    try:
        regime = (build_regime_map(benchmark)
                  if _cfg.REGIME_FILTER_ENABLED and benchmark is not None else None)
        nifty = benchmark if _cfg.RS_FILTER_ENABLED else None

        t0 = time.time()
        sim = simulate(data, nifty_df=nifty, regime_ok=regime,
                       trailing_exit=_cfg.TRAILING_EXIT_ENABLED)
        m = metrics_mod.compute_metrics(sim["trade_log"], sim["equity_curve"],
                                        sim["positions_count"], INITIAL_CAPITAL)

        min_len = min(len(df) for df in data.values())
        seg_pfs, seg_trades = [], []
        for start, end in split_indices(min_len, N_SEGMENTS):
            data_slice = {s: df.iloc[start:end] for s, df in data.items()}
            stats = _segment_stats(data_slice, nifty_df=nifty, regime_ok=regime)
            seg_pfs.append(stats["pf"])
            seg_trades.append(stats["trades"])
        verdict = evaluate_segments(seg_pfs[0], seg_pfs[1:], in_sample_trades=seg_trades[0])

        mar = m["mar_ratio"]
        mar_s = "inf" if mar == float("inf") else f"{mar:.2f}"
        segs = ", ".join(f"{p:.2f}({t})" for p, t in zip(seg_pfs, seg_trades))
        low = " LOW-SAMPLE-IS" if verdict.get("low_sample") else ""
        print(f"  [{name}] {time.time() - t0:.0f}s | trades={m['total_trades']} "
              f"CAGR={m['cagr_pct']:+.2f}% MDD={m['max_drawdown_pct']:.2f}% MAR={mar_s} "
              f"Sharpe={m['sharpe']:.2f} | segPF=[{segs}] "
              f"OOS={'PASS' if verdict['passed'] else 'FAIL'}{low}", flush=True)
        return {"metrics": m, "segment_pfs": seg_pfs, "segment_trades": seg_trades,
                "oos_passed": verdict["passed"], "low_sample": verdict.get("low_sample", False)}
    finally:
        for attr, value in saved.items():
            setattr(_cfg, attr, value)


def _print_table(results: dict) -> None:
    print("\n" + "=" * 104)
    print(f"{'VARIANT':<12} {'TRADES':>6} {'WIN%':>6} {'PF':>6} {'EXP%':>6} "
          f"{'CAGR%':>7} {'MDD%':>6} {'MAR':>6} {'SHARPE':>7} {'EXPO%':>6} {'OOS':>6}")
    print("-" * 104)
    for name, r in results.items():
        m = r["metrics"]
        pf = m["profit_factor"]
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        mar = m["mar_ratio"]
        mar_s = "inf" if mar == float("inf") else f"{mar:.2f}"
        oos = ("PASS" if r["oos_passed"] else "FAIL") + ("*" if r.get("low_sample") else "")
        print(f"{name:<12} {m['total_trades']:>6} {m['win_rate_pct']:>6.1f} {pf_s:>6} "
              f"{m['expectancy_pct']:>6.2f} {m['cagr_pct']:>7.2f} {m['max_drawdown_pct']:>6.2f} "
              f"{mar_s:>6} {m['sharpe']:>7.2f} {m['exposure_pct']:>6.1f} {oos:>6}")
    print("=" * 104)
    print("  * absolute OOS floor (PF >= 1.0) used because the in-sample segment "
          "had too few trades for the ratio test.")


def main(days: int = 1200) -> dict:
    print(f"Loading universe ({len(WATCHLIST)} symbols, {days}d)...", flush=True)
    data = load_universe(WATCHLIST, days, get_ohlcv_free, STRATEGY_MODE)
    print(f"  {len(data)} symbols passed filters.", flush=True)
    benchmark = fetch_benchmark(days)
    print(f"  benchmark bars: {0 if benchmark is None else len(benchmark)}", flush=True)

    results: dict = {}
    for name, overrides in VARIANTS:
        print(f"\n=== {name} {overrides or '(adopted base)'} ===", flush=True)
        results[name] = _run_variant(name, overrides, data, benchmark)

    _print_table(results)
    return results


if __name__ == "__main__":
    main()
