# Quick Reference: RELAXED Mode Usage

## How to Switch Modes

### Step 1: Edit Configuration
Open [`config.py`](d:\trading\config.py) and change:

```python
# For STRICT mode (current settings)
STRATEGY_MODE: str = "STRICT"

# For RELAXED mode (easier entry criteria)
STRATEGY_MODE: str = "RELAXED"
```

### Step 2: Run Your System

**Paper Trading** (uses mode from config):
```bash
python paper_trade/paper_engine.py
```

**Backtest** (specific mode):
```python
from backtest.engine import run_backtest

# STRICT mode
results = run_backtest(strategy_mode="STRICT")

# RELAXED mode
results = run_backtest(strategy_mode="RELAXED")
```

**Compare Both Modes**:
```bash
python compare_modes.py
```

---

## Mode Comparison

| Aspect | STRICT | RELAXED |
|--------|--------|---------|
| **Trade Frequency** | ~1 trade/25 days | ~1 trade/6 days |
| **Win Rate** | 52.63% | 57.04% |
| **Total Return** | 76.53% | 3,717.83% |
| **Max Drawdown** | 17.51% | 28.92% |
| **RSI Range** | 42-60 | 38-65 |
| **Pullback** | 5-10% | 3-8% |
| **ADX** | >18 | >15 |
| **Volume** | 300k avg | 200k avg |
| **EMA** | >50 & >200 | >50 only |

---

## Key Differences

### STRICT Mode
- ✅ Lower risk, higher conviction
- ✅ Conservative drawdown (17.51%)
- ❌ Fewer trading opportunities
- ❌ Lower total returns

### RELAXED Mode
- ✅ More trading opportunities
- ✅ Higher win rate (57.04%)
- ✅ Much higher returns (3,717.83%)
- ❌ Higher drawdown (28.92%)
- ❌ More frequent monitoring needed

---

## Recommendation

**Start with RELAXED mode** for paper trading to:
- See more frequent signals
- Test the system in different market conditions
- Build confidence with higher win rate
- Achieve target trade frequency

**Switch to STRICT mode** if:
- You want more conservative trading
- You prefer lower drawdown
- You have limited capital
- You want higher conviction setups

---

## Files Created

- `trades_log_strict.csv` - STRICT mode backtest results
- `trades_log_relaxed.csv` - RELAXED mode backtest results
- `compare_modes.py` - Run both backtests
- `analyze_results.py` - Analyze results
- `RELAXED_MODE_SUMMARY.md` - Full documentation

---

## Quick Commands

```bash
# Run paper trading (uses config mode)
python paper_trade/paper_engine.py

# Run STRICT backtest
python -c "from backtest.engine import run_backtest; run_backtest(strategy_mode='STRICT')"

# Run RELAXED backtest
python -c "from backtest.engine import run_backtest; run_backtest(strategy_mode='RELAXED')"

# Compare both modes
python compare_modes.py

# Analyze results
python analyze_results.py
```
