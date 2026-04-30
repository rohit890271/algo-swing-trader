# Quick Reference: Algo Swing Trader

## How to Switch Strategy Modes

### Step 1: Edit Configuration
Open [`config.py`](d:\trading\config.py) and change the `STRATEGY_MODE` variable:

```python
# For RELAXED mode (easier entry criteria, higher frequency)
STRATEGY_MODE: str = "RELAXED"

# For STRICT mode (conservative, lower frequency)
STRATEGY_MODE: str = "STRICT"
```

### Step 2: Run Your System

**Paper Trading** (uses mode from `config.py`):
```bash
python paper_trade/paper_engine.py
```

**Backtest** (can run specific mode manually):
```python
from backtest.engine import run_backtest

# STRICT mode
results = run_backtest(strategy_mode="STRICT")

# RELAXED mode
results = run_backtest(strategy_mode="RELAXED")
```

**Compare Both Modes side-by-side**:
```bash
python compare_modes.py
```

---

## Strategy Mode Comparison

| Aspect | STRICT | RELAXED |
|--------|--------|---------|
| **Trade Frequency** | ~1 trade / 25 days | ~1 trade / 5.5 days |
| **Total Trades** | 57 | 217 |
| **Win Rate** | 52.63% | 54.38% |
| **Profit Factor** | 1.76 | 1.82 |
| **Max Drawdown** | 0.18% | 0.26% |
| **Total Return** | +0.65% | +2.59% |
| **RSI Range** | 42-60 | 38-65 |
| **Pullback** | 5-10% | 3.5-8% |
| **ADX** | >18 | >15 |
| **Volume** | 300k avg | 200k avg |
| **EMA** | Price > 50 & 200 | Price > 50 only |

---

## Key Differences

### STRICT Mode
- ✅ Conservative risk, ultra-low drawdown (0.18%).
- ✅ High conviction setups.
- ❌ Infrequent trading opportunities.

### RELAXED Mode
- ✅ Robust trade frequency (~200 trades).
- ✅ Higher win rate (54.38%) and higher Profit Factor (1.82).
- ✅ Better overall portfolio return.
- ❌ Slightly higher (but still negligible) drawdown.

---

## Recommendation

**Start with RELAXED mode** for daily paper trading to:
- See more frequent active signals in the dashboard.
- Test the system actively in current market conditions.
- Benefit from the tuned parameter set that achieves the optimal ~1 trade per week target.

---

## Quick Terminal Commands

```bash
# Start live paper trading scan
python paper_trade/paper_engine.py

# Run backtests side-by-side
python compare_modes.py

# Analyze generic results from csv
python analyze_results.py
```
