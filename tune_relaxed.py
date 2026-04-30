"""
Tune RELAXED mode parameters step by step.

Each step runs as a SUBPROCESS so the config override is seen
by a fresh Python interpreter — no importlib caching issues.

Steps:
  1. RELAXED_PULLBACK_MIN  3.0 -> 4.0
  2. RELAXED_MIN_AVG_VOLUME 200k -> 300k  (cumulative with step 1)
  3. RELAXED_ADX_MIN       15.0 -> 17.0   (cumulative)

Stop as soon as trades land in [180, 220].
"""

from __future__ import annotations

import subprocess
import sys
import os
import json

ROOT   = os.path.abspath(os.path.dirname(__file__))
PY     = sys.executable
STEP_RUNNER = os.path.join(ROOT, "_tune_step_runner.py")

TARGET_LOW  = 180
TARGET_HIGH = 220

# ── Write the per-step runner script ──────────────────────────
RUNNER_CODE = '''\
"""Single-step backtest runner. Reads overrides from env vars, runs RELAXED backtest, prints JSON."""
import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

import config

# Apply overrides from env
overrides = json.loads(os.environ.get("TUNE_OVERRIDES", "{}"))
for k, v in overrides.items():
    setattr(config, k, v)

# NOW import engine (after config is patched at module level)
from config import WATCHLIST
from backtest.engine import run_backtest

result = run_backtest(
    watchlist=WATCHLIST,
    days=1200,
    save_csv=False,
    strategy_mode="RELAXED",
)

s   = result["summary"]
pf  = s.get("profit_factor", 0)
out = {
    "total_trades":    s["total_trades"],
    "win_rate_pct":    s["win_rate_pct"],
    "profit_factor":   pf if pf != float("inf") else "inf",
    "max_drawdown_pct": s["max_drawdown_pct"],
    "total_return_pct": s["total_return_pct"],
}
# Print JSON on its own line so parent can parse it
print("##RESULT##" + json.dumps(out))
'''

with open(STEP_RUNNER, "w") as f:
    f.write(RUNNER_CODE)


# ── Steps: each entry is (label, cumulative_overrides_dict) ──

STEPS = [
    (
        "STEP 1 — Pullback floor 3% -> 4%",
        {
            "RELAXED_PULLBACK_MIN": 4.0,
        },
    ),
    (
        "STEP 2 — Volume filter 200k -> 300k  (+step 1)",
        {
            "RELAXED_PULLBACK_MIN":   4.0,
            "RELAXED_MIN_AVG_VOLUME": 300_000,
        },
    ),
    (
        "STEP 3 — ADX floor 15 -> 17  (+steps 1+2)",
        {
            "RELAXED_PULLBACK_MIN":   4.0,
            "RELAXED_MIN_AVG_VOLUME": 300_000,
            "RELAXED_ADX_MIN":        17.0,
        },
    ),
]


def run_step(label: str, overrides: dict) -> dict:
    """Spawn subprocess with overrides in env, parse JSON result."""
    env = os.environ.copy()
    env["TUNE_OVERRIDES"] = json.dumps(overrides)

    print(f"\n{'=' * 62}")
    print(f"  {label}")
    for k, v in overrides.items():
        fmt_v = f"{v:,}" if isinstance(v, int) else str(v)
        print(f"    {k} = {fmt_v}")
    print(f"{'=' * 62}")
    print("  Running backtest... (this takes ~5 min)")

    proc = subprocess.run(
        [PY, STEP_RUNNER],
        cwd=ROOT,
        env=env,
        capture_output=False,   # let yfinance progress bars stream through
        text=True,
    )

    # Read output captured to file
    result_line = None
    output_file = os.path.join(ROOT, "_tune_last_output.txt")

    # Re-run capturing output to parse result line
    proc2 = subprocess.run(
        [PY, STEP_RUNNER],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    for line in proc2.stdout.splitlines():
        if line.startswith("##RESULT##"):
            result_line = line[len("##RESULT##"):]
            break

    if result_line is None:
        print("  [ERROR] Could not parse result from subprocess.")
        print("  STDERR:", proc2.stderr[-2000:] if proc2.stderr else "none")
        return {}

    return json.loads(result_line)


def print_result(label: str, r: dict) -> None:
    pf_s = f"{r['profit_factor']:.2f}" if isinstance(r["profit_factor"], float) else r["profit_factor"]
    print(f"\n  +--------------------------------------------------+")
    print(f"  |  RESULT: {label}")
    print(f"  +--------------------------------------------------+")
    print(f"  |  Total Trades  : {r['total_trades']:<32}|")
    print(f"  |  Win Rate      : {r['win_rate_pct']:.2f}%{'':<29}|")
    print(f"  |  Profit Factor : {pf_s:<32}|")
    print(f"  |  Max Drawdown  : {r['max_drawdown_pct']:.2f}%{'':<29}|")
    print(f"  |  Total Return  : {r['total_return_pct']:+.2f}%{'':<29}|")
    print(f"  +--------------------------------------------------+")
    n = r["total_trades"]
    if TARGET_LOW <= n <= TARGET_HIGH:
        print(f"  [TARGET HIT]  {n} trades is within {TARGET_LOW}-{TARGET_HIGH}. Stop here.")
    elif n < TARGET_LOW:
        print(f"  [UNDER] {n} trades < {TARGET_LOW}. Too many removed.")
    else:
        print(f"  [OVER]  {n} trades > {TARGET_HIGH}. Continue tuning.")


def main():
    print("\n" + "=" * 62)
    print("  RELAXED MODE STEP-BY-STEP PARAMETER TUNING")
    print(f"  Target: {TARGET_LOW}-{TARGET_HIGH} trades")
    print("  Note: Each step runs in a fresh subprocess.")
    print("=" * 62)

    final_overrides = {}
    final_result    = {}

    for label, overrides in STEPS:
        r = run_step(label, overrides)
        if not r:
            print("  Aborting due to subprocess error.")
            break

        print_result(label, r)
        n = r["total_trades"]

        if TARGET_LOW <= n <= TARGET_HIGH:
            final_overrides = overrides
            final_result    = r
            break
        elif n < TARGET_LOW:
            # Rolled too far — keep previous step's overrides
            print(f"\n  Previous step was the sweet spot. Using those params.")
            break
        else:
            final_overrides = overrides
            final_result    = r

    # ── Final report ────────────────────────────────────────────
    print("\n\n" + "=" * 62)
    print("  FINAL TUNED RELAXED PARAMETERS")
    print("=" * 62)
    defaults = {
        "RELAXED_PULLBACK_MIN":   3.0,
        "RELAXED_PULLBACK_MAX":   8.0,
        "RELAXED_ADX_MIN":       15.0,
        "RELAXED_MIN_AVG_VOLUME": 200_000,
    }
    merged = {**defaults, **final_overrides}
    for k, v in merged.items():
        fmt_v = f"{v:,}" if isinstance(v, int) else str(v)
        print(f"  {k:<28} = {fmt_v}")
    print("-" * 62)
    if final_result:
        pf_s = f"{final_result['profit_factor']:.2f}" if isinstance(final_result["profit_factor"], float) else final_result["profit_factor"]
        print(f"  Total Trades   : {final_result['total_trades']}")
        print(f"  Win Rate       : {final_result['win_rate_pct']:.2f}%")
        print(f"  Profit Factor  : {pf_s}")
        print(f"  Max Drawdown   : {final_result['max_drawdown_pct']:.2f}%")
        print(f"  Total Return   : {final_result['total_return_pct']:+.2f}%")
    print("=" * 62)

    n = final_result.get("total_trades", 0)
    if TARGET_LOW <= n <= TARGET_HIGH:
        print(f"\n  [SUCCESS] {n} trades is within target {TARGET_LOW}-{TARGET_HIGH}.")
        print("\n  >> Apply these values to config.py RELAXED section:")
        for k, v in merged.items():
            fmt_v = f"{v:,}" if isinstance(v, int) else str(v)
            print(f"     {k} = {fmt_v}")
    else:
        print(f"\n  [REVIEW NEEDED] Final count {n} outside {TARGET_LOW}-{TARGET_HIGH}.")
        print("  All 3 steps exhausted. Consider a mid-point between step 2 and 3.")

    # Cleanup runner
    try:
        os.remove(STEP_RUNNER)
    except OSError:
        pass


if __name__ == "__main__":
    main()
