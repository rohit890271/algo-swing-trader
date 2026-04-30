"""
Configuration module for the algorithmic swing trading system.

All tunable parameters — indicator thresholds, capital allocation,
risk management percentages, and broker settings — are defined here
as module-level constants so every other module imports a single
source of truth.
"""

# ──────────────────────────────────────────────
# Capital & Portfolio
# ──────────────────────────────────────────────
INITIAL_CAPITAL: float = 100000.0          # INR
MAX_OPEN_POSITIONS: int = 4                # max concurrent trades overall
MAX_SECTOR_POSITIONS: int = 2              # max concurrent trades in the same sector
POSITION_RISK_PCT: float = 0.75            # risk 0.75 % of capital per trade
MAX_PORTFOLIO_RISK_PCT: float = 5.0        # max 5 % total portfolio risk

# ──────────────────────────────────────────────
# EMA Periods
# ──────────────────────────────────────────────
EMA_FAST: int = 20
EMA_MEDIUM: int = 50
EMA_SLOW: int = 200

# ──────────────────────────────────────────────
# RSI
# ──────────────────────────────────────────────
RSI_PERIOD: int = 14
RSI_OVERSOLD: float = 30.0
RSI_OVERBOUGHT: float = 70.0

# ──────────────────────────────────────────────
# Volume Analysis
# ──────────────────────────────────────────────
VOLUME_MA_PERIOD: int = 20
VOLUME_SPIKE_MULTIPLIER: float = 1.5       # ≥ 1.5× avg volume = spike

# ──────────────────────────────────────────────
# Risk / Stop-Loss
# ──────────────────────────────────────────────
ATR_PERIOD: int = 14
ATR_STOP_MULTIPLIER: float = 2.0           # SL = entry ± 2 × ATR
TRAILING_STOP_PCT: float = 3.0             # 3 % trailing stop
REWARD_RISK_RATIO: float = 2.0             # minimum R:R for a trade

# ──────────────────────────────────────────────
# Strategy Mode
# ──────────────────────────────────────────────
STRATEGY_MODE: str = "STRICT"  # "STRICT" or "RELAXED"

# STRICT Mode Parameters (Current Settings)
STRICT_RSI_MIN: float = 42.0
STRICT_RSI_MAX: float = 60.0
STRICT_PULLBACK_MIN: float = 5.0
STRICT_PULLBACK_MAX: float = 10.0
STRICT_ADX_MIN: float = 18.0
STRICT_MIN_AVG_VOLUME: int = 300_000

# RELAXED Mode Parameters (Easier Entry)
RELAXED_RSI_MIN: float = 38.0
RELAXED_RSI_MAX: float = 65.0
RELAXED_PULLBACK_MIN: float = 3.5
RELAXED_PULLBACK_MAX: float = 8.0
RELAXED_ADX_MIN: float = 15.0
RELAXED_MIN_AVG_VOLUME: int = 200_000

# ──────────────────────────────────────────────
# Backtest
# ──────────────────────────────────────────────
COMMISSION_PCT: float = 0.03               # brokerage + charges (%)
SLIPPAGE_PCT: float = 0.05                 # estimated slippage (%)
PAPER_TRADE: bool = True                   # True = no real orders placed
MAX_HOLD_DAYS: int = 7                    # max trading days to hold a swing trade

# ──────────────────────────────────────────────
# Watchlists (NSE symbols to scan)
# ──────────────────────────────────────────────

LARGECAP_100 = [
    # Nifty 50
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BHARTIARTL", 
    "BPCL", "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", 
    "DRREDDY", "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", 
    "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", 
    "INDUSINDBK", "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", 
    "LT", "M&M", "MARUTI", "NESTLEIND", "NTPC", 
    "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", 
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS", 
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
    # Nifty Next 50
    "ABB", "ADANIENSOL", "ADANIGREEN", "ADANIPOWER", "AMBUJACEM", 
    "ATGL", "AUBANK", "BAJAJHLDNG", "BANKBARODA", "BERGEPAINT", 
    "BOSCHLTD", "CANBK", "CHOLAFIN", "COLPAL", "DLF", 
    "DABUR", "GAIL", "GODREJCP", "HAVELLS", "HAL", 
    "ICICIGI", "ICICIPRULI", "IDBI", "INDIGO", "IRCTC", 
    "IRFC", "JINDALSTEL", "JIOFIN", "LICI", "LODHA", 
    "MARICO", "MUTHOOTFIN", "NAUKRI", "PAYTM", "PIDILITIND", 
    "PNB", "RECLTD", "SBICARD", "SHREECEM", "SIEMENS", 
    "TORNTPHARM", "TVSMOTOR", "UBL", "UNITDSPR", "VEDL", "ZOMATO"
]

MIDCAP_50 = [
    "ABBOTINDIA", "ALKEM", "APOLLOTYRE", "ASHOKLEY", "ASTRAL", 
    "AUROPHARMA", "BALKRISIND", "BANDHANBNK", "BANKINDIA", "BATAINDIA", 
    "BHARATFORG", "BHEL", "BIOCON", "CANBK", "CHOLAFIN", 
    "COFORGE", "CONCOR", "COROMANDEL", "CROMPTON", "CUMMINSIND", 
    "DALBHARAT", "DELHIVERY", "DIXON", "ESCORTS", "FEDERALBNK", 
    "GODREJPROP", "GUJGASLTD", "HAL", "IDEA", "IDFCFIRSTB", 
    "INDHOTEL", "INDUSTOWER", "JSWENERGY", "JUBLFOOD", "LAURUSLABS", 
    "LICHSGFIN", "LUPIN", "M&MFIN", "MAXHEALTH", "PAGEIND", 
    "PERSISTENT", "PETRONET", "PIIND", "POLYCAB", "RECLTD", 
    "SAIL", "SYNGENE", "TVSMOTOR", "UBL", "VOLTAS", "ZEEL"
]

# Combined master list: Nifty 100 + Midcap 50 only (no small-caps)
WATCHLIST: list = sorted(list(set(LARGECAP_100 + MIDCAP_50)))

# ──────────────────────────────────────────────
# Volume Filter
# ──────────────────────────────────────────────
MIN_AVG_VOLUME: int = 300_000              # skip stocks with 20-day avg vol < 300k (STRICT mode)


# ──────────────────────────────────────────────
# Zerodha / Kite Connect
# ──────────────────────────────────────────────
KITE_API_KEY: str = "YOUR_API_KEY"
KITE_API_SECRET: str = "YOUR_API_SECRET"
KITE_ACCESS_TOKEN: str = ""                # populated at runtime
KITE_EXCHANGE: str = "NSE"
KITE_PRODUCT: str = "CNC"                  # CNC for delivery, MIS for intraday
KITE_ORDER_VARIETY: str = "regular"
