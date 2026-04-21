"""
Risk management utilities — position sizing and stop-loss calculation.

Every trade's size is derived from the *fixed-fractional* method:
risk a constant percentage of current capital on each trade, with
the stop-loss distance dictating how many shares to buy.

Dependencies: pandas, numpy
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import (
    POSITION_RISK_PCT,
    MAX_PORTFOLIO_RISK_PCT,
    MAX_OPEN_POSITIONS,
    MAX_SECTOR_POSITIONS,
    ATR_STOP_MULTIPLIER,
    TRAILING_STOP_PCT,
    REWARD_RISK_RATIO,
    ATR_PERIOD,
)


@dataclass
class TradeRisk:
    """Container for a single trade's risk parameters.

    Attributes:
        entry_price:    Planned or actual entry price.
        stop_loss:      Absolute stop-loss price.
        take_profit:    Absolute take-profit target price.
        position_size:  Number of shares / lots to trade.
        risk_amount:    Capital at risk (INR) for this trade.
    """

    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: int
    risk_amount: float


# ──────────────────────────────────────────────
# Stop Loss
# ──────────────────────────────────────────────

def calculate_stop_loss(
    entry_price: float,
    stop_pct: float = 0.03,
) -> float:
    """Calculate a percentage-based stop-loss price below the entry.

    The stop is placed ``stop_pct × 100`` percent below the entry
    price.  For example, the default ``0.03`` (3 %) applied to an
    entry of ₹1 000 yields a stop at ₹970.

    Args:
        entry_price: Trade entry price (must be > 0).
        stop_pct:    Fractional stop distance, e.g. ``0.03`` for 3 %.
                     Must be in the open interval (0, 1).

    Returns:
        The absolute stop-loss price.

    Raises:
        ValueError: If *entry_price* ≤ 0 or *stop_pct* is not in (0, 1).
    """
    if entry_price <= 0:
        raise ValueError(
            f"entry_price must be > 0, got {entry_price}"
        )
    if not (0 < stop_pct < 1):
        raise ValueError(
            f"stop_pct must be between 0 and 1 (exclusive), got {stop_pct}"
        )
    return round(entry_price * (1 - stop_pct), 2)


def calculate_atr_stop_loss(
    entry_price: float,
    atr_value: float,
    atr_multiplier: float = 1.5,
    max_stop_pct: float = 0.04,
    min_stop_pct: float = 0.015,
) -> float:
    """Calculate a volatility-adaptive stop-loss using ATR.

    The raw stop distance is ``atr_multiplier x ATR(14)``, but it is
    clamped between *min_stop_pct* and *max_stop_pct* of the entry
    price so the stop never becomes unreasonably tight or wide.

    Formula::

        raw_stop   = entry_price - (atr_multiplier x atr_value)
        raw_pct    = (entry_price - raw_stop) / entry_price
        clamped    = clamp(raw_pct, min_stop_pct, max_stop_pct)
        stop_price = entry_price x (1 - clamped)

    Args:
        entry_price:    Trade entry price (must be > 0).
        atr_value:      Current ATR(14) value (must be > 0).
        atr_multiplier: ATR multiplier (default ``1.5``).
        max_stop_pct:   Maximum stop distance as a fraction of entry
                        (default ``0.04`` = 4 %).
        min_stop_pct:   Minimum stop distance as a fraction of entry
                        (default ``0.015`` = 1.5 %).

    Returns:
        The absolute stop-loss price, rounded to 2 decimal places.

    Raises:
        ValueError: If any input fails validation.

    Example::

        >>> calculate_atr_stop_loss(1000.0, atr_value=25.0)
        962.5   # 1000 - (1.5 x 25) = 962.5  -> 3.75%, within 1.5-4%
        >>> calculate_atr_stop_loss(1000.0, atr_value=5.0)
        985.0   # raw = 0.75%, clamped to floor 1.5%
        >>> calculate_atr_stop_loss(1000.0, atr_value=50.0)
        960.0   # raw = 7.5%, capped to ceiling 4%
    """
    if entry_price <= 0:
        raise ValueError(f"entry_price must be > 0, got {entry_price}")
    if atr_value <= 0:
        raise ValueError(f"atr_value must be > 0, got {atr_value}")
    if atr_multiplier <= 0:
        raise ValueError(f"atr_multiplier must be > 0, got {atr_multiplier}")

    # Raw stop distance as a fraction of entry
    raw_stop_pct = (atr_multiplier * atr_value) / entry_price

    # Clamp between floor and ceiling
    clamped_pct = max(min_stop_pct, min(raw_stop_pct, max_stop_pct))

    return round(entry_price * (1 - clamped_pct), 2)


def atr_stop_loss(
    entry_price: float,
    atr_value: float,
    side: int = 1,
    multiplier: float = ATR_STOP_MULTIPLIER,
) -> float:
    """Calculate a stop-loss price based on ATR.

    For a **long** trade the stop sits *below* the entry price;
    for a **short** trade it sits *above*.

    Args:
        entry_price: Trade entry price.
        atr_value:   Current ATR value for the instrument.
        side:        ``1`` for long, ``-1`` for short.
        multiplier:  ATR multiple for stop distance (default from config).

    Returns:
        The absolute stop-loss price.
    """
    stop_distance = atr_value * multiplier
    return entry_price - (side * stop_distance)


def percentage_stop_loss(
    entry_price: float,
    pct: float = TRAILING_STOP_PCT,
    side: int = 1,
) -> float:
    """Calculate a simple percentage-based stop-loss price.

    Args:
        entry_price: Trade entry price.
        pct:         Percentage distance for the stop (e.g. ``3.0`` → 3 %).
        side:        ``1`` for long, ``-1`` for short.

    Returns:
        The absolute stop-loss price.
    """
    return entry_price * (1 - side * pct / 100.0)


# ──────────────────────────────────────────────
# Target Price
# ──────────────────────────────────────────────

def calculate_target(
    entry_price: float,
    target_pct: float = 0.08,
) -> float:
    """Calculate a percentage-based take-profit target above the entry.

    The target is placed ``target_pct × 100`` percent above the entry
    price.  For example, the default ``0.08`` (8 %) applied to an
    entry of ₹1 000 yields a target at ₹1 080.

    Args:
        entry_price: Trade entry price (must be > 0).
        target_pct:  Fractional target distance, e.g. ``0.08`` for 8 %.
                     Must be > 0.

    Returns:
        The absolute target price.

    Raises:
        ValueError: If *entry_price* ≤ 0 or *target_pct* ≤ 0.
    """
    if entry_price <= 0:
        raise ValueError(
            f"entry_price must be > 0, got {entry_price}"
        )
    if target_pct <= 0:
        raise ValueError(
            f"target_pct must be > 0, got {target_pct}"
        )
    return round(entry_price * (1 + target_pct), 2)


# ──────────────────────────────────────────────
# Trailing Stop
# ──────────────────────────────────────────────

def trailing_stop(
    entry_price: float,
    current_price: float,
    trail_pct: float = 0.03,
) -> dict:
    """Compute a trailing stop that activates only after a minimum gain.

    The trailing stop **activates** once ``current_price`` reaches at
    least ``entry_price × 1.04`` (4 % gain).  Before that threshold
    the function returns an *inactive* result so the caller can fall
    back to a fixed stop-loss.

    When active, the trailing stop sits ``trail_pct × 100`` percent
    below ``current_price``.

    Args:
        entry_price:   Original trade entry price (must be > 0).
        current_price: Latest market price (must be > 0).
        trail_pct:     Fractional trailing distance, e.g. ``0.03``
                       for 3 %.  Must be in (0, 1).

    Returns:
        A dict with keys:

        * ``"active"``     – ``True`` if the trailing stop is engaged.
        * ``"stop_price"`` – The trailing stop-loss price (``None``
          when inactive).
        * ``"gain_pct"``   – Current unrealised gain as a percentage.

    Raises:
        ValueError: If any input fails validation.
    """
    if entry_price <= 0:
        raise ValueError(
            f"entry_price must be > 0, got {entry_price}"
        )
    if current_price <= 0:
        raise ValueError(
            f"current_price must be > 0, got {current_price}"
        )
    if not (0 < trail_pct < 1):
        raise ValueError(
            f"trail_pct must be between 0 and 1 (exclusive), got {trail_pct}"
        )

    activation_price = entry_price * 1.04  # 4 % gain threshold
    gain_pct = ((current_price - entry_price) / entry_price) * 100.0

    if current_price >= activation_price:
        stop_price = round(current_price * (1 - trail_pct), 2)
        return {
            "active": True,
            "stop_price": stop_price,
            "gain_pct": round(gain_pct, 2),
        }

    return {
        "active": False,
        "stop_price": None,
        "gain_pct": round(gain_pct, 2),
    }


def trailing_stop_update(
    current_stop: float,
    current_price: float,
    trail_pct: float = TRAILING_STOP_PCT,
    side: int = 1,
) -> float:
    """Return an updated trailing stop-loss price.

    The stop only ever moves in the direction of profit — it never
    retreats.  (Used internally by the backtest engine.)

    Args:
        current_stop:  Existing stop-loss price.
        current_price: Latest market price.
        trail_pct:     Trailing distance as a percentage.
        side:          ``1`` for long, ``-1`` for short.

    Returns:
        The new (potentially tightened) stop-loss price.
    """
    new_stop = current_price * (1 - side * trail_pct / 100.0)
    if side == 1:
        return max(current_stop, new_stop)
    return min(current_stop, new_stop)


# ──────────────────────────────────────────────
# Take Profit
# ──────────────────────────────────────────────

def take_profit_price(
    entry_price: float,
    stop_loss: float,
    rr_ratio: float = REWARD_RISK_RATIO,
    side: int = 1,
) -> float:
    """Compute a take-profit target given entry, stop, and desired R:R.

    Args:
        entry_price: Trade entry price.
        stop_loss:   Stop-loss price.
        rr_ratio:    Reward-to-Risk ratio (e.g. ``2.0`` → 2:1).
        side:        ``1`` for long, ``-1`` for short.

    Returns:
        The absolute take-profit price.
    """
    risk = abs(entry_price - stop_loss)
    return entry_price + (side * risk * rr_ratio)


# ──────────────────────────────────────────────
# Position Sizing (fixed-fractional)
# ──────────────────────────────────────────────

def position_size(
    capital: float,
    entry_price: float,
    stop_loss_price: float,
    risk_pct: float = 0.01,
) -> int:
    """Calculate position size so maximum loss equals *risk_pct* of capital.

    Formula::

        shares = (capital × risk_pct) / |entry_price − stop_loss_price|

    The result is floored to a whole number of shares.

    Args:
        capital:         Current portfolio equity in INR (must be > 0).
        entry_price:     Planned entry price (must be > 0).
        stop_loss_price: Planned stop-loss price (must be > 0 and
                         ≠ *entry_price*).
        risk_pct:        Fraction of capital to risk per trade,
                         e.g. ``0.01`` for 1 % (default).  Must be
                         in the open interval (0, 1).

    Returns:
        Number of shares to buy (integer, ≥ 0).

    Raises:
        ValueError: If any input fails validation.
    """
    if capital <= 0:
        raise ValueError(f"capital must be > 0, got {capital}")
    if entry_price <= 0:
        raise ValueError(f"entry_price must be > 0, got {entry_price}")
    if stop_loss_price <= 0:
        raise ValueError(
            f"stop_loss_price must be > 0, got {stop_loss_price}"
        )
    if entry_price == stop_loss_price:
        raise ValueError(
            "entry_price and stop_loss_price must differ "
            f"(both are {entry_price})"
        )
    if not (0 < risk_pct < 1):
        raise ValueError(
            f"risk_pct must be between 0 and 1 (exclusive), got {risk_pct}"
        )

    risk_amount = capital * risk_pct
    risk_per_share = abs(entry_price - stop_loss_price)
    return int(risk_amount / risk_per_share)


def max_position_value(
    capital: float,
    open_positions: int = 0,
) -> float:
    """Return the maximum value a single new position may carry.

    This ensures total portfolio exposure stays within
    ``MAX_PORTFOLIO_RISK_PCT`` and position count within
    ``MAX_OPEN_POSITIONS``.

    Args:
        capital:        Current portfolio equity.
        open_positions: Number of positions already held.

    Returns:
        Maximum allowed position value in INR.
    """
    remaining_slots = max(0, MAX_OPEN_POSITIONS - open_positions)
    if remaining_slots == 0:
        return 0.0
    max_exposure = capital * (MAX_PORTFOLIO_RISK_PCT / 100.0)
    return max_exposure / remaining_slots


def can_open_new_position(
    total_open_positions: int,
    sector_open_positions: int,
) -> bool:
    """Determine if a new position is permitted under portfolio constraints.

    Checks two constraints:
      1. Overall open positions must be < MAX_OPEN_POSITIONS
      2. Open positions in the same sector must be < MAX_SECTOR_POSITIONS

    Args:
        total_open_positions: Current total trade count.
        sector_open_positions: Current trade count in the prospective stock's sector.

    Returns:
        True if the trade is permitted, False otherwise.
    """
    if total_open_positions >= MAX_OPEN_POSITIONS:
        return False
    if sector_open_positions >= MAX_SECTOR_POSITIONS:
        return False
    return True


# ──────────────────────────────────────────────
# Convenience builder
# ──────────────────────────────────────────────

def build_trade_risk(
    capital: float,
    entry_price: float,
    atr_value: float,
    side: int = 1,
) -> TradeRisk:
    """Construct a complete :class:`TradeRisk` for a prospective trade.

    Combines ATR-based stop-loss, R:R-based take-profit, and
    fixed-fractional position sizing into a single object.

    Args:
        capital:     Current portfolio equity (INR).
        entry_price: Planned entry price.
        atr_value:   Current ATR value for the instrument.
        side:        ``1`` for long, ``-1`` for short.

    Returns:
        A fully populated :class:`TradeRisk` instance.
    """
    sl = atr_stop_loss(entry_price, atr_value, side=side)
    tp = take_profit_price(entry_price, sl, side=side)
    qty = position_size(capital, entry_price, sl)
    risk_amt = abs(entry_price - sl) * qty

    return TradeRisk(
        entry_price=entry_price,
        stop_loss=round(sl, 2),
        take_profit=round(tp, 2),
        position_size=qty,
        risk_amount=round(risk_amt, 2),
    )
