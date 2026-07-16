"""
Entry and exit signal generation for the swing trading strategy.

The strategy is a pullback-in-uptrend screener.  ``check_entry_signal``
evaluates the latest bar against a set of mode-dependent conditions and
``check_exit_signal`` returns a priority-ordered exit reason for an open
position.  Both operate on a single symbol's enriched OHLCV DataFrame.

Dependencies: pandas
"""

from __future__ import annotations

import pandas as pd

import config as _config   # read Phase 2 flags dynamically (testable via monkeypatch)
from config import (
    STRICT_RSI_MIN,
    STRICT_RSI_MAX,
    STRICT_PULLBACK_MIN,
    STRICT_PULLBACK_MAX,
    STRICT_ADX_MIN,
    STRICT_MIN_AVG_VOLUME,
    RELAXED_RSI_MIN,
    RELAXED_RSI_MAX,
    RELAXED_PULLBACK_MIN,
    RELAXED_PULLBACK_MAX,
    RELAXED_ADX_MIN,
    RELAXED_MIN_AVG_VOLUME,
)


# ──────────────────────────────────────────────
# Pullback entry screener (single-bar verdict)
# ──────────────────────────────────────────────

def check_entry_signal(df: pd.DataFrame, nifty_df: pd.DataFrame | None = None, strategy_mode: str = "STRICT") -> dict:
    """Evaluate the *latest bar* of an OHLCV DataFrame against a set of
    swing-trade entry conditions.

    The function computes all required indicators internally, so the
    caller may pass a **raw** OHLCV DataFrame (columns: ``open``,
    ``high``, ``low``, ``close``, ``volume``).

    **Entry conditions vary by strategy mode:**

    **STRICT Mode (default):**
    All 9 conditions must be True for a BUY signal:
    1. Close is above both EMA-50 and EMA-200 (uptrend).
    2. EMA-20 is above EMA-50 (short-term momentum).
    3. Price has pulled back 5-10% from the rolling 10-day high.
    4. RSI (14) is between 42 and 60 (not overbought, not oversold).
    5. The last 3 candles show declining volume **and** today's volume
       is above its own 5-day average (volume dry-up then expansion).
    6. Today's candle is bullish (close > open).
    7. Not in freefall (1-week return > -5%).
    8. At least 1 pullback day before today.
    9. ADX (14) > 18 (confirms a trending market, not sideways).

    **RELAXED Mode:**
    All 9 conditions must be True for a BUY signal:
    1. Close is above EMA-50 (uptrend - EMA-200 requirement removed).
    2. EMA-20 is above EMA-50 (short-term momentum).
    3. Price has pulled back 3-8% from the rolling 10-day high.
    4. RSI (14) is between 38 and 65 (wider range).
    5. The last 3 candles show declining volume **and** today's volume
       is above its own 5-day average (volume dry-up then expansion).
    6. Today's candle is bullish (close > open).
    7. Not in freefall (1-week return > -5%).
    8. At least 1 pullback day before today.
    9. ADX (14) > 15 (easier trend requirement).

    Args:
        df:       OHLCV ``pandas.DataFrame`` with a DatetimeIndex.  Must
                  contain at least 200 rows for the slowest EMA to warm up.
        nifty_df: Optional OHLCV DataFrame for the Nifty 50 index
                  (``^NSEI``), sliced up to the signal date.  Used by the
                  optional relative-strength condition when
                  ``config.RS_FILTER_ENABLED`` is on; otherwise ignored.
        strategy_mode: "STRICT" or "RELAXED" - determines entry criteria.

    Returns:
        A dict with two keys:

        * ``"signal"`` -- ``True`` if all conditions are met, else ``False``.
        * ``"reason"`` -- A human-readable string listing which conditions
          passed or failed.

    Example::

        >>> result = check_entry_signal(ohlcv_df, nifty_df, "RELAXED")
        >>> if result["signal"]:
        ...     print("Entry triggered:", result["reason"])
    """
    # -- Set parameters based on strategy mode --
    if strategy_mode == "RELAXED":
        rsi_min = RELAXED_RSI_MIN
        rsi_max = RELAXED_RSI_MAX
        pullback_min = RELAXED_PULLBACK_MIN
        pullback_max = RELAXED_PULLBACK_MAX
        adx_min = RELAXED_ADX_MIN
        require_ema200 = False
    else:  # STRICT mode (default)
        rsi_min = STRICT_RSI_MIN
        rsi_max = STRICT_RSI_MAX
        pullback_min = STRICT_PULLBACK_MIN
        pullback_max = STRICT_PULLBACK_MAX
        adx_min = STRICT_ADX_MIN
        require_ema200 = True

    # -- Compute or use pre-calculated indicators -
    if "ema_20" not in df.columns:
        from strategy.indicators import enrich_with_indicators
        data = enrich_with_indicators(df)
    else:
        data = df

    # Latest bar values
    latest  = data.iloc[-1]
    close   = latest["close"]
    open_   = latest["open"]
    ema20   = latest["ema_20"]
    ema50   = latest["ema_50"]
    ema200  = latest["ema_200"]
    rsi_val = latest["rsi"]
    adx_val = latest["adx"]
    volume  = latest["volume"]

    reasons: list[str] = []

    # -- Condition 1: Close > EMA-50 (and EMA-200 in STRICT mode) --
    cond1 = close > ema50
    if require_ema200:
        cond1 = cond1 and (close > ema200)
        reasons.append(
            f"{'[PASS]' if cond1 else '[FAIL]'} Close ({close:.2f}) "
            f"{'above' if cond1 else 'NOT above'} EMA-50 ({ema50:.2f}) "
            f"& EMA-200 ({ema200:.2f})"
        )
    else:
        reasons.append(
            f"{'[PASS]' if cond1 else '[FAIL]'} Close ({close:.2f}) "
            f"{'above' if cond1 else 'NOT above'} EMA-50 ({ema50:.2f})"
        )

    # -- Condition 2: EMA-20 > EMA-50 --------
    cond2 = ema20 > ema50
    reasons.append(
        f"{'[PASS]' if cond2 else '[FAIL]'} EMA-20 ({ema20:.2f}) "
        f"{'above' if cond2 else 'NOT above'} EMA-50 ({ema50:.2f})"
    )

    # -- Condition 3: Pullback range (varies by mode) --
    high_10d = latest["high_10d"]
    pullback_pct = ((high_10d - close) / high_10d) * 100.0
    cond3 = pullback_min <= pullback_pct <= pullback_max
    reasons.append(
        f"{'[PASS]' if cond3 else '[FAIL]'} Pullback {pullback_pct:.2f}% from "
        f"10-day high ({high_10d:.2f}) -- need {pullback_min}-{pullback_max}%"
    )

    # -- Condition 4: RSI range (varies by mode) --
    cond4 = rsi_min <= rsi_val <= rsi_max
    reasons.append(
        f"{'[PASS]' if cond4 else '[FAIL]'} RSI ({rsi_val:.2f}) "
        f"{'inside' if cond4 else 'outside'} {rsi_min}-{rsi_max} range"
    )

    # -- Condition 5: Last 3 candles declining volume + today > 5-day avg --
    vol_series = data["volume"]
    declining_vol = (
        vol_series.iloc[-4] > vol_series.iloc[-3]
        and vol_series.iloc[-3] > vol_series.iloc[-2]
    )
    vol_avg_5 = latest["vol_avg_5d"]   # 5-day avg *before* today
    vol_expansion = volume > vol_avg_5
    cond5 = declining_vol and vol_expansion
    reasons.append(
        f"{'[PASS]' if declining_vol else '[FAIL]'} Last 3 candles declining volume | "
        f"{'[PASS]' if vol_expansion else '[FAIL]'} Today vol ({volume:,.0f}) "
        f"{'>' if vol_expansion else '<='} 5-day avg ({vol_avg_5:,.0f})"
    )

    # -- Condition 6: Bullish candle (close > open) --
    cond6 = close > open_
    reasons.append(
        f"{'[PASS]' if cond6 else '[FAIL]'} Bullish candle -- "
        f"Close ({close:.2f}) {'>' if cond6 else '<='} Open ({open_:.2f})"
    )

    # -- Condition 7: Not in freefall (1-week return > -5%) --
    if len(data) >= 5:
        week_return = latest["return_1w_pct"]
        cond7 = week_return > -5.0
        reasons.append(
            f"{'[PASS]' if cond7 else '[FAIL]'} 1-week return {week_return:+.2f}% "
            f"-- need > -5%"
        )
    else:
        cond7 = True
        reasons.append("[SKIP] 1-week return -- not enough data")

    # -- Condition 8: at least 1 pullback day before today --
    cond8 = data["close"].iloc[-2] < data["close"].iloc[-3]
    reasons.append(
        f"{'[PASS]' if cond8 else '[FAIL]'} 1 pullback day "
        f"before entry candle"
    )

    # -- Condition 9: ADX threshold (varies by mode) --
    cond9 = adx_val > adx_min
    reasons.append(
        f"{'[PASS]' if cond9 else '[FAIL]'} ADX ({adx_val:.2f}) "
        f"{'>' if cond9 else '<='} {adx_min} -- {'trending' if cond9 else 'sideways'}"
    )

    # -- Condition 10 (optional, Phase 2 H3): relative strength vs index --
    # Only trade stocks outperforming the benchmark over the lookback window.
    cond10 = True
    if _config.RS_FILTER_ENABLED and nifty_df is not None:
        lookback = _config.RS_LOOKBACK_DAYS
        if len(data) > lookback and len(nifty_df) > lookback:
            stock_ret = (data["close"].iloc[-1] / data["close"].iloc[-lookback - 1] - 1) * 100.0
            nifty_ret = (nifty_df["close"].iloc[-1] / nifty_df["close"].iloc[-lookback - 1] - 1) * 100.0
            cond10 = stock_ret > nifty_ret
            reasons.append(
                f"{'[PASS]' if cond10 else '[FAIL]'} RS {stock_ret:+.2f}% vs "
                f"Nifty {nifty_ret:+.2f}% over {lookback}d"
            )
        else:
            reasons.append("[SKIP] RS filter -- not enough data")

    # -- Composite verdict --------------------
    signal = all([cond1, cond2, cond3, cond4, cond5, cond6, cond7, cond8, cond9, cond10])
    summary = f"ALL CONDITIONS MET - ENTRY ({strategy_mode} MODE)" if signal else f"Entry conditions NOT met ({strategy_mode} MODE)"

    return {
        "signal": signal,
        "reason": f"{summary}\n" + "\n".join(reasons),
    }


# ──────────────────────────────────────────────
# Exit condition screener (single-bar verdict)
# ──────────────────────────────────────────────

def check_exit_signal(
    df: pd.DataFrame,
    entry_price: float,
    entry_date,
    stop_loss: float,
    target: float,
    max_hold_days: int = 7,
    partial_taken: bool = False,
) -> str:
    """Evaluate the latest bar and return an exit reason string.

    The function checks conditions in **priority order** and returns
    the first one that fires.  If nothing triggers, ``"HOLD"`` is
    returned.

    Priority order:

    1. ``"TARGET_HIT"``        -- close >= *target*.
    2. ``"STOP_LOSS"``         -- close <= *stop_loss*.
    3. ``"PARTIAL_EXIT_5PCT"`` -- profit >= 5 % and partial exit not
                                  yet taken (*partial_taken* is False).
    4. ``"TIME_EXIT"``         -- trading days since *entry_date*
                                  >= *max_hold_days* (default 7).
    5. ``"MOMENTUM_FADE"``     -- RSI (14) drops below 45 after entry
                                  (momentum has faded).
    6. ``"RSI_OVERBOUGHT"``    -- RSI (14) crosses above 70.
    7. ``"BEARISH_REVERSAL"``  -- a bearish engulfing candle forms
                                  near a local resistance level
                                  (20-bar rolling high).
    8. ``"HOLD"``              -- none of the above.

    Args:
        df:             OHLCV ``pandas.DataFrame`` with a DatetimeIndex.
        entry_price:    The price at which the position was opened.
        entry_date:     The date/timestamp the position was opened.
        stop_loss:      Absolute stop-loss price.
        target:         Absolute take-profit target price.
        max_hold_days:  Maximum number of **trading** (business) days
                        to hold the position (default ``7``).
        partial_taken:  Whether a partial exit (50 %) has already been
                        booked for this trade.  When ``False`` and
                        profit >= 5 %, returns ``"PARTIAL_EXIT_5PCT"``.

    Returns:
        One of the following literal strings:

        * ``"TARGET_HIT"``
        * ``"STOP_LOSS"``
        * ``"PARTIAL_EXIT_5PCT"``
        * ``"TIME_EXIT"``
        * ``"MOMENTUM_FADE"``
        * ``"RSI_OVERBOUGHT"``
        * ``"BEARISH_REVERSAL"``
        * ``"HOLD"``

    Raises:
        ValueError: If *df* has fewer than 2 rows.
    """
    from strategy.indicators import rsi as compute_rsi  # avoid circular import

    if len(df) < 2:
        raise ValueError(
            f"DataFrame must have >= 2 rows for exit checks, got {len(df)}"
        )

    latest = df.iloc[-1]
    prev   = df.iloc[-2]
    close  = latest["close"]

    # -- 1. TARGET_HIT ------------------------
    if close >= target:
        return "TARGET_HIT"

    # -- 2. STOP_LOSS -------------------------
    if close <= stop_loss:
        return "STOP_LOSS"

    # -- 3. PARTIAL_EXIT_5PCT -----------------
    current_pnl_pct = ((close - entry_price) / entry_price) * 100.0
    if not partial_taken and current_pnl_pct >= 5.0:
        return "PARTIAL_EXIT_5PCT"

    # -- 4. TIME_EXIT -------------------------
    entry_ts  = pd.Timestamp(entry_date)
    latest_ts = pd.Timestamp(df.index[-1])
    trading_days = len(pd.bdate_range(start=entry_ts, end=latest_ts)) - 1
    if trading_days >= max_hold_days:
        return "TIME_EXIT"

    # -- 5. MOMENTUM_FADE (RSI < 45) ---------
    if "rsi" in df.columns:
        rsi_now  = latest["rsi"]
        rsi_prev = prev["rsi"]
    else:
        from strategy.indicators import rsi as compute_rsi
        rsi_series = compute_rsi(df["close"], period=14)
        rsi_now  = rsi_series.iloc[-1]
        rsi_prev = rsi_series.iloc[-2]
        
    if rsi_now < 45:
        return "MOMENTUM_FADE"

    # -- 6. RSI_OVERBOUGHT (cross above 70) --
    if rsi_now > 70 and rsi_prev <= 70:
        return "RSI_OVERBOUGHT"

    # -- 7. BEARISH_REVERSAL ------------------
    bearish_engulfing = (
        latest["open"] > prev["close"]
        and latest["close"] < prev["open"]
        and prev["close"] > prev["open"]   # previous was bullish
        and latest["close"] < latest["open"]  # today is bearish
    )
    if bearish_engulfing:
        if "high_20d" in df.columns:
            resistance = latest["high_20d"]
        else:
            resistance = df["high"].rolling(window=20).max().iloc[-1]
            
        near_resistance = (resistance - close) / resistance <= 0.01
        if near_resistance:
            return "BEARISH_REVERSAL"

    # -- 8. Nothing triggered -----------------
    return "HOLD"
