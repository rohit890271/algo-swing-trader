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
MAX_OPEN_POSITIONS: int = 2
POSITION_RISK_PCT: float = 1.0             # risk 1 % of capital per trade
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
# Backtest
# ──────────────────────────────────────────────
COMMISSION_PCT: float = 0.03               # brokerage + charges (%)
SLIPPAGE_PCT: float = 0.05                 # estimated slippage (%)
PAPER_TRADE: bool = True                   # True = no real orders placed
MAX_HOLD_DAYS: int = 10                    # max trading days to hold a swing trade

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

SMALLCAP_50 = [
    "ANGELONE", "ANURAS", "BSE", "CDSL", "CENTRALBK", 
    "CESC", "CHAMBLFERT", "CAMS", "CYIENT", "EIDPARRY", 
    "FACT", "FSL", "GLENMARK", "GMDCLTD", "GNFC", 
    "HFCL", "HGS", "HINDCOPPER", "IDFC", "IIFL", 
    "INDIACEM", "JBCHEPHARM", "JSL", "KARURVYSYA", "KEI", 
    "LATENTVIEW", "MAHABANK", "METROBRAND", "NBCC", "NEOGEN", 
    "NHPC", "NLCINDIA", "PVRINOX", "RADICO", "REDINGTON", 
    "RITES", "RTNINDIA", "SJVN", "SONACOMS", "SUZLON", 
    "SYRMA", "TEJASNET", "TRIDENT", "UCOBANK", "UTIAMC", 
    "WELCORP", "WELSPUNIND", "ZENSARTECH"
]

BSE_SMALLCAP_50 = [
    "AHLUCONT.BO", "ALLCARGO.BO", "BAJAJCON.BO", "BDL.BO", "BORORENEW.BO", 
    "BSOFT.BO", "CAPLIPOINT.BO", "CASTROLIND.BO", "CENTURYPLY.BO", "CHALET.BO", 
    "CHENNPETRO.BO", "CIGNITITEC.BO", "COCHINSHIP.BO", "CSBBANK.BO", "CUB.BO", 
    "DATAMATICS.BO", "EQUITASBNK.BO", "EVEREADY.BO", "FINCABLES.BO", "GODFRYPHLP.BO", 
    "GSFC.BO", "HEG.BO", "HSCL.BO", "IFBIND.BO", "IGPL.BO", 
    "INDOCO.BO", "ISEC.BO", "JBMA.BO", "JKPAPER.BO", "JKLAKSHMI.BO", 
    "JUBLPHARMA.BO", "KALYANKJIL.BO", "KOLTEPATIL.BO", "LINDEINDIA.BO", "MASTEK.BO", 
    "MOIL.BO", "NETWORK18.BO", "NIITLTD.BO", "OLECTRA.BO", "OMAXE.BO", 
    "PNCINFRA.BO", "PRSMJOHNSN.BO", "RAILTEL.BO", "RALLIS.BO", "RATEGAIN.BO", 
    "SIS.BO", "SOBHA.BO", "TIMKEN.BO", "UJJIVANSFB.BO", "VIPIND.BO"
]

# Combined master list (using set to remove any overlaps, sorted for alphabetical order)
WATCHLIST: list = sorted(list(set(LARGECAP_100 + MIDCAP_50 + SMALLCAP_50 + BSE_SMALLCAP_50)))


# ──────────────────────────────────────────────
# Zerodha / Kite Connect
# ──────────────────────────────────────────────
KITE_API_KEY: str = "YOUR_API_KEY"
KITE_API_SECRET: str = "YOUR_API_SECRET"
KITE_ACCESS_TOKEN: str = ""                # populated at runtime
KITE_EXCHANGE: str = "NSE"
KITE_PRODUCT: str = "CNC"                  # CNC for delivery, MIS for intraday
KITE_ORDER_VARIETY: str = "regular"
