# Pre-Deployment Strategy Program — Design Spec

**Date:** 2026-06-21
**Status:** Phases 1–2 implemented; Phase 3 pending
**Author:** brainstormed with Claude

> **Phase 2 outcome (2026-07-16):** hypotheses tested one-at-a-time via
> `backtest/phase2_experiments.py` against the walk-forward OOS guardrail.
> Regime filter (H1) + trailing exits (H2) adopted as defaults:
> MAR 0.21→0.59, Sharpe 0.47→0.90, win 63.0%, PF 2.85, expectancy
> +2.31%/trade, MDD 8.40%, OOS segment PFs 3.36/3.51. Relative strength (H3)
> degraded OOS results and was rejected. The pre-committed deployability bar
> (OOS MAR ≥ ~0.8) was **not** met (0.59) — the 4-week forward paper test and
> any real-money decision must weigh that explicitly.

## Context

`D:\trading` is an algorithmic swing-trading system for Indian equities (NSE). It scans
Nifty 100 + Midcap 50 for pullback-in-uptrend setups, backtests them, and runs a daily
paper-trading scan. No real orders are placed today (the broker layer is a stub; data comes
from Yahoo Finance via `get_ohlcv_free`).

The user wants to deploy **real money**, but:

- There is **no recently-run, trusted backtest baseline**.
- Git history shows parameter tuning aimed at hitting a trade-count target
  ("iterative parameter tuning to optimize trade frequency") — a known overfitting smell.
- Position size will **follow confidence** — capital is not fixed; it scales with how
  trustworthy the validated results are.

## Goal

Build *justified confidence* before risking money. Confidence is the deliverable; returns are
secondary until the edge is proven real.

## Decision: Approach A — Validation-first, strictly phased

Three sequential sub-projects, each with its own spec → plan → implementation cycle:

1. **Phase 1 — Validate:** make the backtest honest and establish a trusted baseline.
2. **Phase 2 — Strengthen:** improve the edge *only* on the validated foundation (regime
   filters, entries/exits, sizing). Out of scope for this spec.
3. **Phase 3 — Harden + Go-live:** equity tracking, broker execution wiring, monitoring,
   fail-safes, and a staged small-capital rollout. Out of scope for this spec.

We do not touch strategy logic or write any broker call until Phase 1 produces a baseline we
believe. Approaches B (parallel hardening) and C (strengthen-first) were rejected: both risk
polishing a strategy that honest validation may invalidate.

**User-confirmed assumptions:**
- The honest backtest will likely show *worse* numbers than today's — accepted.
- Survivorship bias will be acknowledged and haircut, not solved with paid point-in-time data.

---

## Phase 1 — Make the Backtest Honest & Establish a Trusted Baseline

### The core problem

`backtest/engine.py` simulates **each symbol independently with unlimited capital and zero
trading costs**. It can hold every symbol at once, ignores the ₹100k account and the
`MAX_OPEN_POSITIONS = 4` cap that the live paper engine enforces, and books raw price moves.
Results are therefore structurally optimistic. Phase 1 rebuilds the backtest to trade the way
a real account would.

### Components

#### 1. Portfolio-level backtest engine (primary change)

Replace the per-symbol independent loop with a single **date-driven** simulation across the
whole universe:

- One shared capital account, starting at `INITIAL_CAPITAL` (₹100k).
- Respect `MAX_OPEN_POSITIONS`; optionally `MAX_SECTOR_POSITIONS` if a sector map is supplied
  (otherwise skip sector cap and note it).
- Each trading day, in order: (a) process exits for open positions, (b) gather eligible entry
  candidates from the universe, (c) rank them (deterministic rule, e.g. highest pass-strength
  / proximity to setup; documented), (d) open positions up to remaining capacity.
- Position sizing uses **current equity** (true fixed-fractional via `POSITION_RISK_PCT`),
  not a fixed `INITIAL_CAPITAL` per trade.
- Produces a single real equity curve → real CAGR, max drawdown, Sharpe, exposure.

This subsumes the previously-identified "no capital persistence" issue at the backtest level.

#### 2. Realistic fills (eliminate look-ahead)

The current engine enters at the **close of the signal bar** — impossible to execute, because
that same close is what confirms the signal. Changes:

- **Entries** fill at the **next bar's open**.
- **Stop-loss / target** resolve against the **next bar's high/low** (intrabar), with a
  documented rule for the ambiguous case where both are touched in one bar (assume the worse
  outcome — stop first — to stay conservative).
- **Signal-based exits** (momentum fade, RSI, reversal, time) execute at the **next open**.

#### 3. Costs & slippage

Apply the already-defined-but-unused config constants on both entry and exit:
`COMMISSION_PCT = 0.03%` + `SLIPPAGE_PCT = 0.05%`, i.e. ≈ 0.16% round-trip, deducted from each
trade's realized P&L and reflected in the equity curve.

#### 4. Survivorship-bias handling

Point-in-time index constituents are not available, so we will not fake precision. Instead:

- Document the bias explicitly in the tear-sheet output.
- Apply a configurable sensitivity **haircut** to headline returns.
- Sanity-check the strategy on a broader, fixed universe that includes historically weak names.

#### 5. Walk-forward as the headline metric

Rework `backtest/walk_forward.py` to use **strict, non-overlapping** train/test splits and emit
an explicit **pass/fail on out-of-sample degradation** (e.g. OOS profit factor / win rate must
not fall below a defined fraction of in-sample). The trusted baseline is the **out-of-sample**
number, never the in-sample one.

#### 6. Trusted baseline tear-sheet

A single reproducible command produces one report covering, all portfolio-level and
**after costs**: total trades, win rate, profit factor, average win/loss, expectancy, max
drawdown, CAGR, Sharpe, exposure %, and the in-sample-vs-out-of-sample comparison. This report
is *the baseline* against which every future (Phase 2) change is judged.

#### 7. Forward paper-test gate

Add minimal **running-equity tracking** to `paper_trade/paper_engine.py` so a 4-week forward
paper-test records real cumulative P&L (not per-run resets). Define explicit go/no-go criteria
comparing live forward expectancy against the backtest baseline expectancy. The full live-grade
equity/portfolio engine remains Phase 3; this is the minimum needed to *measure* the forward
test.

**Recommended gate:** run the forward paper-test for ~4 weeks (a few dozen portfolio trades
given ~1 entry / 5–6 days per name across ~150 names) before any real capital; then deploy
small, with size following confidence.

### Testing

Extend the existing pytest suite (`tests/`) with deterministic synthetic data:

- Portfolio engine never exceeds `MAX_OPEN_POSITIONS`.
- Trading costs reduce realized P&L by the expected amount.
- No same-bar entry — fills occur on the next bar's open.
- Equity compounding is correct across a known sequence of trades.
- Walk-forward pass/fail logic triggers correctly on a constructed degrading series.

Network-dependent code (yfinance, scheduler) stays uncovered by design.

### Explicitly NOT in Phase 1 (YAGNI)

- No new indicators or signal changes (Phase 2).
- No live broker order placement (Phase 3).
- No purchase/integration of point-in-time constituent data.
- No parameter tuning or metric-chasing — the original overfitting trap.

### Phase 1 success criteria

One reproducible command produces a portfolio-level, cost-inclusive, look-ahead-free backtest
plus a walk-forward tear-sheet, covered by tests, that we believe reflects reality. When that
exists and the out-of-sample numbers are understood, Phase 1 is done and a trusted baseline
exists. Phase 2 (Strengthen) may then begin.

## Open questions deferred to later phases

- Exact ranking rule when more entry candidates than open slots exist (decide during Phase 1
  implementation; default: rank by setup quality, document the tiebreak).
- Sector map source for `MAX_SECTOR_POSITIONS` (Phase 3 / optional).
- Live broker (Zerodha Kite) execution, auth-token refresh, and order reconciliation (Phase 3).
