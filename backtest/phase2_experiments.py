"""Phase 2 experiment driver: control vs each edge hypothesis, one data fetch.

Fetches the universe and the Nifty benchmark ONCE, then for each variant
(hypothesis flags toggled on the config module) runs the full portfolio
simulation plus a 3-segment walk-forward, and prints a side-by-side
comparison table.  Selection discipline lives in the Phase 2 plan: a variant
is kept only if it passes the OOS guardrail AND improves OOS profit factor /
expectancy / MAR versus CONTROL.

Usage::

    python -m backtest.phase2_experiments
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

FLAG_NAMES = ("REGIME_FILTER_ENABLED", "TRAILING_EXIT_ENABLED", "RS_FILTER_ENABLED")

VARIANTS = [
    ("CONTROL", {}),
    ("H1_REGIME", {"REGIME_FILTER_ENABLED": True}),
    ("H2_TRAILING", {"TRAILING_EXIT_ENABLED": True}),
    ("H3_RS", {"RS_FILTER_ENABLED": True}),
    ("H1_H2", {"REGIME_FILTER_ENABLED": True, "TRAILING_EXIT_ENABLED": True}),
    ("ALL_THREE", {name: True for name in FLAG_NAMES}),
]


def _run_variant(name: str, flags: dict, data: dict, benchmark) -> dict:
    """Run one variant (full sim + walk-forward) with the given flags applied."""
    saved = {flag: getattr(_cfg, flag) for flag in FLAG_NAMES}
    for flag in FLAG_NAMES:
        setattr(_cfg, flag, flags.get(flag, False))
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
        seg_pfs = []
        seg_trades = []
        for start, end in split_indices(min_len, N_SEGMENTS):
            data_slice = {s: df.iloc[start:end] for s, df in data.items()}
            stats = _segment_stats(data_slice, nifty_df=nifty, regime_ok=regime)
            seg_pfs.append(stats["pf"])
            seg_trades.append(stats["trades"])
        verdict = evaluate_segments(seg_pfs[0], seg_pfs[1:],
                                    in_sample_trades=seg_trades[0])

        mar = m["mar_ratio"]
        mar_s = "inf" if mar == float("inf") else f"{mar:.2f}"
        segs = ", ".join(f"{p:.2f}({t})" for p, t in zip(seg_pfs, seg_trades))
        low = " LOW-SAMPLE-IS" if verdict.get("low_sample") else ""
        print(f"  [{name}] {time.time() - t0:.0f}s | trades={m['total_trades']} "
              f"CAGR={m['cagr_pct']:+.2f}% MDD={m['max_drawdown_pct']:.2f}% MAR={mar_s} "
              f"| seg PF(trades)=[{segs}] "
              f"OOS={'PASS' if verdict['passed'] else 'FAIL'}{low}", flush=True)
        return {"metrics": m, "segment_pfs": seg_pfs, "segment_trades": seg_trades,
                "oos_passed": verdict["passed"],
                "low_sample": verdict.get("low_sample", False)}
    finally:
        for flag, value in saved.items():
            setattr(_cfg, flag, value)


def _print_table(results: dict) -> None:
    print("\n" + "=" * 112)
    print(f"{'VARIANT':<12} {'TRADES':>6} {'WIN%':>6} {'PF':>6} {'EXP%':>6} "
          f"{'CAGR%':>7} {'MDD%':>6} {'MAR':>6} {'SHARPE':>7} {'EXPO%':>6} "
          f"{'SEG PF(trades)':>26} {'OOS':>5}")
    print("-" * 112)
    for name, r in results.items():
        m = r["metrics"]
        pf = m["profit_factor"]
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        mar = m["mar_ratio"]
        mar_s = "inf" if mar == float("inf") else f"{mar:.2f}"
        segs = "/".join(f"{p:.2f}({t})" for p, t in
                        zip(r["segment_pfs"], r["segment_trades"]))
        oos = "PASS" if r["oos_passed"] else "FAIL"
        if r.get("low_sample"):
            oos += "*"   # * = absolute OOS floor used (thin in-sample sample)
        print(f"{name:<12} {m['total_trades']:>6} {m['win_rate_pct']:>6.1f} {pf_s:>6} "
              f"{m['expectancy_pct']:>6.2f} {m['cagr_pct']:>7.2f} "
              f"{m['max_drawdown_pct']:>6.2f} {mar_s:>6} {m['sharpe']:>7.2f} "
              f"{m['exposure_pct']:>6.1f} {segs:>26} {oos:>5}")
    print("=" * 112)
    print("  * absolute OOS floor (PF >= 1.0) used because the in-sample segment "
          "had too few trades for the ratio test.")


def main(days: int = 1200) -> dict:
    print(f"Loading universe ({len(WATCHLIST)} symbols, {days}d of history)...", flush=True)
    data = load_universe(WATCHLIST, days, get_ohlcv_free, STRATEGY_MODE)
    print(f"  {len(data)} symbols passed filters.", flush=True)
    benchmark = fetch_benchmark(days)
    print(f"  benchmark bars: {0 if benchmark is None else len(benchmark)}", flush=True)
    if benchmark is None:
        print("  [!] No benchmark — H1/H3 variants will run unfiltered and be meaningless.")

    results: dict = {}
    for name, flags in VARIANTS:
        print(f"\n=== {name} {flags or '(baseline)'} ===", flush=True)
        results[name] = _run_variant(name, flags, data, benchmark)

    _print_table(results)
    return results


if __name__ == "__main__":
    main()
