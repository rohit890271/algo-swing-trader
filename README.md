# Algo Swing Trader

A fully automated, quantitative swing trading engine built in Python. This system scans the Nifty 100 & Midcap 50 (or any custom watchlist) for high-probability pullback setups. It includes a rigorous historical backtesting engine and a live paper-trading scheduler that automatically runs daily to log active signals.

## Features

- **Dual Strategy Modes**: 
  - `STRICT`: High-conviction setups, lower frequency (~1 trade per 25 days), ultra-low drawdown.
  - `RELAXED`: Active trading, higher frequency (~1 trade per 5.5 days), robust win rate (54%).
- **Technical Analysis Engine**: Leverages TA-Lib to compute RSI, ADX, EMAs (20, 50, 200), and custom Volume filters.
- **Automated Paper Trading**: Schedules a daily scan at market open (09:20 AM IST) to log actionable `ENTRY` signals and trace reasons for `FAIL` rejections in real-time.
- **Robust Risk Management**: Uses fixed fractional risk sizing (1% risk per trade) and 2x ATR dynamic stop losses to simulate realistic portfolio compounding.
- **Performance Analytics**: Includes comprehensive backtest metrics (Win Rate, Profit Factor, Max Drawdown, Return).

## Installation

1. **Clone the repository** and navigate to the directory:
   ```bash
   git clone <your-repo-url>
   cd trading
   ```

2. **Set up a Virtual Environment**:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

3. **Install Dependencies**:
   This project relies on `TA-Lib` for fast technical indicator computation. A pre-compiled Windows wheel for Python 3.13 is included.
   ```bash
   pip install ta_lib-0.6.8-cp313-cp313-win_amd64.whl
   pip install -r requirements.txt
   ```

## Configuration

Settings are managed in `config.py`. 

**Switching Modes**:
To switch between the conservative and active strategies, change the `STRATEGY_MODE` variable:
```python
STRATEGY_MODE: str = "RELAXED"  # or "STRICT"
```

## Usage

### 1. Paper Trading (Live Daily Scan)
Run the automated scheduler to scan the market every day at 09:20 AM IST. It will print a dashboard of the day's signals and the top 5 closest-to-entry stocks.
```bash
python paper_trade/paper_engine.py
```

### 2. Historical Backtesting
Run the engine on 3+ years of historical data to evaluate performance metrics.
```bash
python backtest/engine.py
```
To run both modes side-by-side and view a comparative breakdown:
```bash
python compare_modes.py
```

## Strategy Logic

The strategy hunts for stocks that are in a strong uptrend but are currently experiencing a short-term pullback.

**Core Rules (RELAXED Mode)**:
- **Trend**: Price > 50-day EMA.
- **Momentum**: 20-day EMA > 50-day EMA.
- **Pullback**: Stock has pulled back between 3.5% and 8.0% from its recent 10-day high.
- **RSI**: RSI is in the "sweet spot" of 38-65.
- **ADX**: Trend strength > 15.
- **Volume**: Average daily volume > 200,000 shares to ensure liquidity.
- **Candle**: Today's candle must be Bullish to confirm the reversal.

**Exits**:
- **Stop Loss**: 2x ATR (Average True Range).
- **Take Profit**: 8% target.
- **Partial Exit**: Sells 50% of the position at 5% profit, trailing the rest.
- **Time Stop**: Exits after 7 days if the trade hasn't resolved.
