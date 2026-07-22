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

## Round 3 — portfolio construction (2026-07-22)

Run on a **117-symbol** universe (13 names failed to download that day), so these
numbers are only comparable **within** the table, not against rounds 1–2.

| Variant | N × risk | CAGR | MDD | MAR | Sharpe |
|---------|----------|------|-----|-----|--------|
| BASE | 4 × 0.750% | 3.35% | 8.48% | 0.40 | 0.68 |
| DIV_6 | 6 × 0.500% | 2.28% | 5.61% | 0.41 | 0.67 |
| DIV_8 | 8 × 0.375% | 1.67% | 4.19% | 0.40 | 0.66 |
| DIV_10 | 10 × 0.300% | 1.36% | 3.12% | 0.44 | 0.68 |
| BASE+YIELD | 4 × 0.750% + 6.5% cash | 8.97% | 5.33% | 1.68 | 1.72 |
| DIV_8+YIELD | 8 × 0.375% + 6.5% cash | 7.65% | 2.25% | 3.40 | 2.88 |

**P1 (diversification) — rejected.** Holding total heat constant, MAR is flat
(0.40 / 0.41 / 0.40 / 0.44). CAGR and drawdown scale *down together* almost
exactly, i.e. more slots at smaller size behaved like de-leveraging, not
diversification. Expected: the positions are all long, same market, same regime
— highly correlated, so splitting the same signal pool into more pieces reduces
return as fast as it reduces variance. Win rate/PF/expectancy barely moved
(62.8%→62.3%, 2.50→2.45), confirming no signal-quality change.

**P2 (idle-cash yield) — real money, but NOT strategy alpha. Do not report it
as strategy MAR.** DIV_8 earns 1.67% CAGR; adding a 6.5% liquid-fund yield on
idle cash lifts it to 7.65% — i.e. **~6 of the 7.65 percentage points are the
savings account, not the bot.** Measured drawdown also shrinks (4.19%→2.25%)
because steady interest offsets equity dips, mathematically flattering MAR to
3.40. Taken at face value this "clears" the 0.8 bar; in substance it does not.

**The uncomfortable implication:** parking 100% in the liquid fund would yield
~6.5% at near-zero drawdown. The strategy's *marginal* contribution over simply
holding cash is roughly 1–1.5 percentage points of CAGR, bought with real
equity risk. On this data the bot barely beats the risk-free alternative.

## Standing conclusion

Disciplined, OOS-guarded research took MAR from 0.21 to ~0.62 — a real,
validated edge (win rate ~66%, PF ~2.9, OOS profit factors 3.4/3.7). It did
**not** reach the pre-committed deployability bar of MAR ≈ 0.8, and three
research rounds across signal rules (H3, ATR trail, regime period) and
portfolio construction (diversification) all failed to close the gap.

Round 3 surfaced the deeper issue: the strategy deploys little capital and its
absolute return is small enough that a liquid fund is a serious competitor.
Signal tweaks and position-count changes cannot fix that — the constraint is
structural (long-only, daily-bar pullbacks on efficient large/midcaps, ~45%
time in market).

Honest options from here, in order of expected value:
1. **Forward paper test** the validated config to see if the edge is real live.
2. **A structurally different program** — different timeframe (weekly),
   setup archetype (breakout), or universe — accepting it is a fresh multi-
   session effort.
3. **Accept that indexing/liquid funds may dominate this strategy** for the
   capital involved. This is a legitimate outcome, not a failure of the work.

What must NOT happen: quoting a yield-inflated MAR (e.g. 3.40) as strategy
performance, or hunting more parameter variants until one clears 0.8.
