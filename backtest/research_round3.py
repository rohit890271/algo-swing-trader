"""Research round 3: portfolio construction.

Signal-rule levers are exhausted (see docs/RESEARCH_LOG.md). This round tests
the *portfolio* axis on top of the adopted H1+H2 config:

  P1  Diversification at CONSTANT total heat -- more slots, proportionally
      smaller risk per trade:  4x0.75% = 6x0.50% = 8x0.375% = 10x0.30% = 3.0%.
      Isolates diversification from leverage. The tradeoff to watch: extra
      slots take lower-ranked signals, so diversification fights signal
      dilution.
  P2  Idle-cash yield -- ~53% of capital sits uninvested. Modelled as an
      overnight/liquid-fund return. This is CASH MANAGEMENT, NOT ALPHA, so it
      is reported as a separate variant and never folded into edge metrics
      (win rate / profit factor / expectancy are unchanged by it).

Same discipline as prior rounds: one lever at a time, judged out-of-sample.

Usage::

    python -m backtest.research_round3
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

TOTAL_HEAT_PCT = 3.0    # 4 slots x 0.75% -- held constant across P1 variants

# (name, max_positions, risk_pct, idle_cash_yield_pct)
VARIANTS = [
    ("BASE",        4,  0.750, 0.0),
    ("DIV_6",       6,  0.500, 0.0),
    ("DIV_8",       8,  0.375, 0.0),
    ("DIV_10",     10,  0.300, 0.0),
    ("BASE+YIELD",  4,  0.750, 6.5),
    ("DIV_8+YIELD", 8,  0.375, 6.5),
]


def _run_variant(name: str, max_positions: int, risk_pct: float,
                 cash_yield: float, data: dict, benchmark) -> dict:
    saved_yield = _cfg.IDLE_CASH_ANNUAL_YIELD_PCT
    _cfg.IDLE_CASH_ANNUAL_YIELD_PCT = cash_yield
    try:
        regime = (build_regime_map(benchmark)
                  if _cfg.REGIME_FILTER_ENABLED and benchmark is not None else None)
        nifty = benchmark if _cfg.RS_FILTER_ENABLED else None

        t0 = time.time()
        sim = simulate(data, nifty_df=nifty, regime_ok=regime,
                       max_positions=max_positions, risk_pct=risk_pct,
                       trailing_exit=_cfg.TRAILING_EXIT_ENABLED)
        m = metrics_mod.compute_metrics(sim["trade_log"], sim["equity_curve"],
                                        sim["positions_count"], INITIAL_CAPITAL)

        min_len = min(len(df) for df in data.values())
        seg_pfs, seg_trades = [], []
        for start, end in split_indices(min_len, N_SEGMENTS):
            data_slice = {s: df.iloc[start:end] for s, df in data.items()}
            stats = _segment_stats(data_slice, nifty_df=nifty, regime_ok=regime,
                                   max_positions=max_positions, risk_pct=risk_pct)
            seg_pfs.append(stats["pf"])
            seg_trades.append(stats["trades"])
        verdict = evaluate_segments(seg_pfs[0], seg_pfs[1:], in_sample_trades=seg_trades[0])

        mar = m["mar_ratio"]
        mar_s = "inf" if mar == float("inf") else f"{mar:.2f}"
        segs = ", ".join(f"{p:.2f}({t})" for p, t in zip(seg_pfs, seg_trades))
        low = " LOW-SAMPLE-IS" if verdict.get("low_sample") else ""
        print(f"  [{name}] {time.time() - t0:.0f}s | N={max_positions} risk={risk_pct}% "
              f"heat={max_positions * risk_pct:.2f}% yield={cash_yield}% | "
              f"trades={m['total_trades']} CAGR={m['cagr_pct']:+.2f}% "
              f"MDD={m['max_drawdown_pct']:.2f}% MAR={mar_s} Sharpe={m['sharpe']:.2f} | "
              f"segPF=[{segs}] OOS={'PASS' if verdict['passed'] else 'FAIL'}{low}", flush=True)
        return {"metrics": m, "segment_pfs": seg_pfs, "segment_trades": seg_trades,
                "oos_passed": verdict["passed"], "low_sample": verdict.get("low_sample", False),
                "n": max_positions, "risk": risk_pct, "yield": cash_yield}
    finally:
        _cfg.IDLE_CASH_ANNUAL_YIELD_PCT = saved_yield


def _print_table(results: dict) -> None:
    print("\n" + "=" * 112)
    print(f"{'VARIANT':<12} {'N':>3} {'RISK%':>6} {'YLD%':>5} {'TRADES':>6} {'WIN%':>6} "
          f"{'PF':>6} {'EXP%':>6} {'CAGR%':>7} {'MDD%':>6} {'MAR':>6} {'SHARPE':>7} "
          f"{'EXPO%':>6} {'OOS':>6}")
    print("-" * 112)
    for name, r in results.items():
        m = r["metrics"]
        pf = m["profit_factor"]
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        mar = m["mar_ratio"]
        mar_s = "inf" if mar == float("inf") else f"{mar:.2f}"
        oos = ("PASS" if r["oos_passed"] else "FAIL") + ("*" if r.get("low_sample") else "")
        print(f"{name:<12} {r['n']:>3} {r['risk']:>6.3f} {r['yield']:>5.1f} "
              f"{m['total_trades']:>6} {m['win_rate_pct']:>6.1f} {pf_s:>6} "
              f"{m['expectancy_pct']:>6.2f} {m['cagr_pct']:>7.2f} {m['max_drawdown_pct']:>6.2f} "
              f"{mar_s:>6} {m['sharpe']:>7.2f} {m['exposure_pct']:>6.1f} {oos:>6}")
    print("=" * 112)
    print("  All P1 variants hold total heat constant at "
          f"{TOTAL_HEAT_PCT:.1f}% (N x risk), isolating diversification from leverage.")
    print("  YLD variants add idle-cash yield: cash management, NOT strategy alpha —")
    print("  win rate / PF / expectancy are unaffected by it; only CAGR and MAR move.")
    print("  * absolute OOS floor (PF >= 1.0) used: in-sample segment too thin for the ratio test.")


def main(days: int = 1200) -> dict:
    print(f"Loading universe ({len(WATCHLIST)} symbols, {days}d)...", flush=True)
    data = load_universe(WATCHLIST, days, get_ohlcv_free, STRATEGY_MODE)
    print(f"  {len(data)} symbols passed filters.", flush=True)
    benchmark = fetch_benchmark(days)
    print(f"  benchmark bars: {0 if benchmark is None else len(benchmark)}", flush=True)

    results: dict = {}
    for name, n, risk, cash_yield in VARIANTS:
        print(f"\n=== {name} (N={n}, risk={risk}%, yield={cash_yield}%) ===", flush=True)
        results[name] = _run_variant(name, n, risk, cash_yield, data, benchmark)

    _print_table(results)
    return results


if __name__ == "__main__":
    main()
