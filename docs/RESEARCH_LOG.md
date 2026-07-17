# Research Log

A durable record of what was tested and *rejected*, so dead ends aren't
re-litigated. Every result below is out-of-sample-guarded via
`backtest/walk_forward.py`; drivers under `backtest/*_experiments.py` /
`research_round2.py` reproduce them.

## Baselines

| Milestone | CAGR | MDD | MAR | Sharpe | Win% | PF | Notes |
|-----------|------|-----|-----|--------|------|----|-------|
| Phase 1 honest baseline | 2.16% | 10.06% | 0.21 | 0.47 | 52.6% | 1.57 | portfolio-level, costs, next-open fills |
| Phase 2 adopted (H1 regime + H2 trailing) | ~5.2% | ~8.4% | **~0.62** | ~0.95 | ~66% | ~2.9 | current `main` default |

## Adopted (2026-07-16)

- **H1 — market regime filter** (`REGIME_FILTER_ENABLED`): no new longs when
  Nifty < its 200-EMA. Big drawdown/Sharpe win.
- **H2 — trailing exits** (`TRAILING_EXIT_ENABLED`): drop the fixed 8% target;
  stop ratchets 3% below close after +4%, momentum-fade ignored, 20-day hold.

## Rejected

| Idea | Flag / param | Result vs base | Why rejected |
|------|--------------|----------------|--------------|
| Relative-strength entry filter (H3) | `RS_FILTER_ENABLED` | MAR 0.62→0.44 (in ALL_THREE); degraded OOS PFs | Filters out too many good pullbacks; hurts OOS |
| ATR-adaptive trailing distance (R-A) | `TRAILING_STOP_MODE="atr"`, mult 2.0/2.5/3.0 | MAR 0.62→0.54–0.56, Sharpe 0.95→~0.85, win 66%→~55% | Wider stops give back more on reversals |
| Regime EMA responsiveness (R-B) | `REGIME_EMA_PERIOD` 50 / 100 | **Identical** to 200 | Inert on 2020–2025 data — index was above all EMAs on the same days |

## Standing conclusion

Disciplined, OOS-guarded research took MAR from 0.21 to ~0.62 — a real,
validated edge (win rate ~66%, PF ~2.9, OOS profit factors 3.4/3.7). It did
**not** reach the pre-committed deployability bar of MAR ≈ 0.8. Further
parameter hunting on this strategy/universe risks curve-fitting; the honest
next step is a forward paper test at the current config, or a *genuinely
different* research program (new universe, timeframe, or setup), not more
tweaks to this one.
