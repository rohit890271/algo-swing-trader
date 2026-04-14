"""
Technical indicator calculations for the swing trading system.

All functions accept a ``pandas.DataFrame`` with at minimum an OHLCV
schema (columns: ``open``, ``high``, ``low``, ``close``, ``volume``)
and return either a ``pandas.Series`` or a modified ``DataFrame``.

Dependencies: pandas, numpy, talib
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib

from config import (
    EMA_FAST,
    EMA_MEDIUM,
    EMA_SLOW,
    RSI_PERIOD,
    VOLUME_MA_PERIOD,
    VOLUME_SPIKE_MULTIPLIER,
    ATR_PERIOD,
)


# ──────────────────────────────────────────────
# Exponential Moving Averages
# ──────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    """Compute Exponential Moving Average using TA-Lib.

    Args:
        series: Price series (typically ``close``).
        period: Look-back window length.

    Returns:
        A ``pandas.Series`` of EMA values aligned with the input index.
    """
    return pd.Series(talib.EMA(series.values, timeperiod=period),
                     index=series.index, name=f"EMA_{period}")


def add_ema_suite(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the three standard EMAs (fast / medium / slow) to *df*.

    Columns added: ``ema_20``, ``ema_50``, ``ema_200`` (names mirror
    the default periods defined in ``config.py``).

    Args:
        df: OHLCV DataFrame.

    Returns:
        The same DataFrame **with** new EMA columns appended.
    """
    df[f"ema_{EMA_FAST}"] = ema(df["close"], EMA_FAST)
    df[f"ema_{EMA_MEDIUM}"] = ema(df["close"], EMA_MEDIUM)
    df[f"ema_{EMA_SLOW}"] = ema(df["close"], EMA_SLOW)
    return df


# ──────────────────────────────────────────────
# Relative Strength Index
# ──────────────────────────────────────────────

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute the Relative Strength Index via TA-Lib.

    Args:
        series: Price series (typically ``close``).
        period: RSI look-back window (default from config).

    Returns:
        A ``pandas.Series`` of RSI values (0–100).
    """
    return pd.Series(talib.RSI(series.values, timeperiod=period),
                     index=series.index, name="RSI")


def add_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    """Attach an RSI column to *df*.

    Args:
        df: OHLCV DataFrame.
        period: RSI look-back window.

    Returns:
        DataFrame with a new ``rsi`` column.
    """
    df["rsi"] = rsi(df["close"], period)
    return df


# ──────────────────────────────────────────────
# Average True Range (used by risk module)
# ──────────────────────────────────────────────

def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Compute Average True Range using TA-Lib.

    Args:
        df: OHLCV DataFrame (needs ``high``, ``low``, ``close``).
        period: ATR look-back window.

    Returns:
        A ``pandas.Series`` of ATR values.
    """
    return pd.Series(
        talib.ATR(df["high"].values, df["low"].values,
                  df["close"].values, timeperiod=period),
        index=df.index,
        name="ATR",
    )


def add_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.DataFrame:
    """Attach an ATR column to *df*.

    Args:
        df: OHLCV DataFrame.
        period: ATR look-back window.

    Returns:
        DataFrame with a new ``atr`` column.
    """
    df["atr"] = atr(df, period)
    return df


# ──────────────────────────────────────────────
# Volume Analysis
# ──────────────────────────────────────────────

def volume_moving_average(
    volume: pd.Series,
    period: int = VOLUME_MA_PERIOD,
) -> pd.Series:
    """Compute a simple moving average of volume.

    Args:
        volume: Raw volume series.
        period: Look-back window for the SMA.

    Returns:
        A ``pandas.Series`` of volume SMA values.
    """
    return volume.rolling(window=period).mean().rename("volume_ma")


def is_volume_spike(
    volume: pd.Series,
    period: int = VOLUME_MA_PERIOD,
    multiplier: float = VOLUME_SPIKE_MULTIPLIER,
) -> pd.Series:
    """Flag bars where volume exceeds *multiplier* × its moving average.

    Args:
        volume:     Raw volume series.
        period:     Look-back window for the volume SMA.
        multiplier: Threshold multiple (default from config).

    Returns:
        A boolean ``pandas.Series`` — ``True`` where a spike occurred.
    """
    vol_ma = volume_moving_average(volume, period)
    return (volume >= vol_ma * multiplier).rename("volume_spike")


def add_volume_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Attach volume-MA and spike-flag columns to *df*.

    Args:
        df: OHLCV DataFrame.

    Returns:
        DataFrame with ``volume_ma`` and ``volume_spike`` columns.
    """
    df["volume_ma"] = volume_moving_average(df["volume"])
    df["volume_spike"] = is_volume_spike(df["volume"])
    return df


def volume_trend(
    volume_series: pd.Series,
    window: int = 5,
) -> pd.Series:
    """Classify the short-term volume trend for each bar.

    Computes a simple linear regression slope of volume over the
    trailing *window* bars and maps the result to one of three
    categorical labels:

    * ``"rising"``   — slope > +1 % of the mean volume in the window.
    * ``"declining"`` — slope < −1 % of the mean volume.
    * ``"flat"``     — everything in between.

    Args:
        volume_series: Raw volume ``pandas.Series``.
        window:        Number of trailing bars to evaluate (default ``5``).

    Returns:
        A ``pandas.Series`` of strings (``"rising"``, ``"flat"``,
        or ``"declining"``) aligned with the input index.
    """
    def _classify_window(w: pd.Series) -> str:
        """Return trend label for a single rolling window."""
        if len(w) < window:
            return "flat"
        x = np.arange(len(w), dtype=float)
        slope = np.polyfit(x, w.values, 1)[0]
        threshold = w.mean() * 0.01        # 1 % of mean volume
        if slope > threshold:
            return "rising"
        elif slope < -threshold:
            return "declining"
        return "flat"

    result = volume_series.rolling(window=window).apply(
        lambda w: {"rising": 1, "flat": 0, "declining": -1}[
            _classify_window(pd.Series(w))
        ],
        raw=False,
    )

    mapping = {1.0: "rising", 0.0: "flat", -1.0: "declining"}
    return result.map(mapping).fillna("flat").rename("volume_trend")


def is_above_ema(
    price: pd.Series,
    ema_50: pd.Series,
    ema_200: pd.Series,
) -> pd.Series:
    """Check whether a bullish trend is confirmed via EMA positioning.

    A bullish trend is confirmed when **both** conditions hold:

    1. The current price is above the 50-period EMA.
    2. The 50-period EMA is above the 200-period EMA (golden cross).

    Args:
        price:   Close price series.
        ema_50:  50-period Exponential Moving Average series.
        ema_200: 200-period Exponential Moving Average series.

    Returns:
        A boolean ``pandas.Series`` — ``True`` where the bullish
        trend is confirmed.
    """
    return ((price > ema_50) & (ema_50 > ema_200)).rename("bullish_trend")


# ──────────────────────────────────────────────
# Convenience: attach ALL indicators at once
# ──────────────────────────────────────────────

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute and attach every indicator used by the strategy.

    This is a convenience wrapper that calls:
    * :func:`add_ema_suite`
    * :func:`add_rsi`
    * :func:`add_atr`
    * :func:`add_volume_analysis`

    Args:
        df: OHLCV DataFrame (columns: open, high, low, close, volume).

    Returns:
        The enriched DataFrame with all indicator columns appended.
    """
    df = add_ema_suite(df)
    df = add_rsi(df)
    df = add_atr(df)
    df = add_volume_analysis(df)
    return df
