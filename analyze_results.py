"""
Quick summary analysis of STRICT vs RELAXED backtest results.
"""

import pandas as pd

# Load both datasets
strict_df = pd.read_csv("trades_log_strict.csv")
relaxed_df = pd.read_csv("trades_log_relaxed.csv")

# Calculate statistics
def analyze_trades(df, mode_name):
    """Analyze trade statistics."""
    if df.empty:
        return None

    total_trades = len(df)
    winners = df[df["pnl_pct"] > 0]
    losers = df[df["pnl_pct"] <= 0]

    win_rate = (len(winners) / total_trades) * 100 if total_trades > 0 else 0
    avg_profit = winners["pnl_pct"].mean() if len(winners) > 0 else 0
    avg_loss = losers["pnl_pct"].mean() if len(losers) > 0 else 0

    # Profit factor
    gross_profit = winners["pnl_pct"].sum()
    gross_loss = abs(losers["pnl_pct"].sum())
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    # Simulate equity-curve based return (same logic as engine.py)
    RISK_PER_TRADE = 0.01
    capital = 100_000.0
    equity = capital
    equity_curve = [capital]
    for pnl in df["pnl_pct"]:
        equity += equity * RISK_PER_TRADE * (pnl / 100.0)
        equity_curve.append(equity)
    import pandas as _pd
    equity_series = _pd.Series(equity_curve)
    running_max = equity_series.cummax()
    drawdown_pct = ((equity_series - running_max) / running_max) * 100.0
    max_drawdown = abs(drawdown_pct.min())
    total_return = ((equity - capital) / capital) * 100.0

    # Calculate trade frequency
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    date_range = (df["entry_date"].max() - df["entry_date"].min()).days
    trade_frequency = date_range / total_trades if total_trades > 0 else 0

    return {
        "mode": mode_name,
        "total_trades": total_trades,
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": win_rate,
        "avg_profit": avg_profit,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "trade_frequency": trade_frequency,
        "date_range_days": date_range
    }

# Analyze both modes
strict_stats = analyze_trades(strict_df, "STRICT")
relaxed_stats = analyze_trades(relaxed_df, "RELAXED")

# Print comparison
print("\n" + "=" * 80)
print("  [BACKTEST RESULTS SUMMARY]")
print("=" * 80)

print(f"\n  {'METRIC':<30} {'STRICT':<20} {'RELAXED':<20} {'CHANGE':<15}")
print("  " + "-" * 80)

# Total trades
print(f"  {'Total Trades':<30} {strict_stats['total_trades']:<20} {relaxed_stats['total_trades']:<20} {relaxed_stats['total_trades'] - strict_stats['total_trades']:+d}")

# Win rate
print(f"  {'Win Rate (%)':<30} {strict_stats['win_rate']:<20.2f} {relaxed_stats['win_rate']:<20.2f} {relaxed_stats['win_rate'] - strict_stats['win_rate']:+.2f}%")

# Average profit
print(f"  {'Avg Profit (win) (%)':<30} {strict_stats['avg_profit']:<20.2f} {relaxed_stats['avg_profit']:<20.2f} {relaxed_stats['avg_profit'] - strict_stats['avg_profit']:+.2f}%")

# Average loss
print(f"  {'Avg Loss (loss) (%)':<30} {strict_stats['avg_loss']:<20.2f} {relaxed_stats['avg_loss']:<20.2f} {relaxed_stats['avg_loss'] - strict_stats['avg_loss']:+.2f}%")

# Profit Factor
strict_pf = strict_stats['profit_factor']
relaxed_pf = relaxed_stats['profit_factor']
strict_pf_str  = f"{strict_pf:.2f}"  if strict_pf  != float('inf') else "inf"
relaxed_pf_str = f"{relaxed_pf:.2f}" if relaxed_pf != float('inf') else "inf"
change_pf = ""
if strict_pf != float('inf') and relaxed_pf != float('inf'):
    change_pf = f"{relaxed_pf - strict_pf:+.2f}"
print(f"  {'Profit Factor':<30} {strict_pf_str:<20} {relaxed_pf_str:<20} {change_pf:<15}")

# Max drawdown
print(f"  {'Max Drawdown (%)':<30} {strict_stats['max_drawdown']:<20.2f} {relaxed_stats['max_drawdown']:<20.2f} {relaxed_stats['max_drawdown'] - strict_stats['max_drawdown']:+.2f}%")

# Total return
print(f"  {'Total Return (%)':<30} {strict_stats['total_return']:<20.2f} {relaxed_stats['total_return']:<20.2f} {relaxed_stats['total_return'] - strict_stats['total_return']:+.2f}%")

print("  " + "-" * 80)

# Trade frequency
print(f"\n  [TRADE FREQUENCY]")
print("  " + "-" * 80)
print(f"  STRICT:  {strict_stats['total_trades']} trades over {strict_stats['date_range_days']} days = 1 trade every {strict_stats['trade_frequency']:.1f} days")
print(f"  RELAXED: {relaxed_stats['total_trades']} trades over {relaxed_stats['date_range_days']} days = 1 trade every {relaxed_stats['trade_frequency']:.1f} days")

print("  " + "-" * 80)

# Target assessment
print(f"\n  [TARGET ASSESSMENT]")
print("  " + "-" * 80)

target_min = 150
target_max = 200
target_freq = 7.0

if relaxed_stats['total_trades'] >= target_min and relaxed_stats['total_trades'] <= target_max:
    print(f"  [PASS] RELAXED mode target MET: {relaxed_stats['total_trades']} trades (target: {target_min}-{target_max})")
elif relaxed_stats['total_trades'] < target_min:
    print(f"  [WARN] RELAXED mode below target: {relaxed_stats['total_trades']} trades (target: {target_min}-{target_max})")
else:
    print(f"  [WARN] RELAXED mode above target: {relaxed_stats['total_trades']} trades (target: {target_min}-{target_max})")

if relaxed_stats['trade_frequency'] <= target_freq + 1.0:
    print(f"  [PASS] Frequency target MET: 1 trade every {relaxed_stats['trade_frequency']:.1f} days (target: {target_freq} days)")
else:
    print(f"  [WARN] Frequency below target: 1 trade every {relaxed_stats['trade_frequency']:.1f} days (target: {target_freq} days)")

print("  " + "-" * 80)

# Key insights
print(f"\n  [KEY INSIGHTS]")
print("  " + "-" * 80)
print(f"  * RELAXED mode generated {relaxed_stats['total_trades'] - strict_stats['total_trades']} additional trades ({(relaxed_stats['total_trades'] / strict_stats['total_trades'] * 100):.1f}% increase)")
print(f"  * Win rate changed by {relaxed_stats['win_rate'] - strict_stats['win_rate']:+.2f}%")
print(f"  * Total return changed by {relaxed_stats['total_return'] - strict_stats['total_return']:+.2f}%")
print(f"  * Trade frequency improved from {strict_stats['trade_frequency']:.1f} to {relaxed_stats['trade_frequency']:.1f} days per trade")

print("  " + "-" * 80)
print("=" * 80 + "\n")
