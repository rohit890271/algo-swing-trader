"""
Zerodha Kite Connect API integration stub.

This module provides a thin wrapper around the ``kiteconnect`` SDK.
All public methods are fully annotated and documented, but the
implementation uses *stub* return values so the project can be
developed and tested without a live broker connection.

Replace the stub bodies with real Kite Connect calls when ready
to go live.

Dependencies: kiteconnect (pip install kiteconnect)
"""

from __future__ import annotations

import logging
import sys
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import (
    KITE_API_KEY,
    KITE_API_SECRET,
    KITE_ACCESS_TOKEN,
    KITE_EXCHANGE,
    KITE_PRODUCT,
    KITE_ORDER_VARIETY,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Order data-class
# ──────────────────────────────────────────────

@dataclass
class OrderResponse:
    """Standardised response returned by order-placement methods.

    Attributes:
        order_id:  Broker-assigned order identifier (empty in stub mode).
        status:    ``"SUCCESS"`` or ``"FAILED"``.
        message:   Human-readable description / error message.
    """

    order_id: str
    status: str
    message: str


# ──────────────────────────────────────────────
# Zerodha API Wrapper
# ──────────────────────────────────────────────

class ZerodhaAPI:
    """Zerodha Kite Connect wrapper for the swing trading system.

    Instantiate this class, then call :meth:`login` to authenticate.
    Subsequent calls to :meth:`place_order`, :meth:`cancel_order`, etc.
    interact with the Kite Connect REST API.

    In **stub mode** (default) every method returns realistic-looking
    dummy data so that the rest of the system can be developed and
    unit-tested offline.

    Args:
        api_key:      Kite Connect API key.
        api_secret:   Kite Connect API secret.
        access_token: Pre-generated session token (optional).
    """

    def __init__(
        self,
        api_key: str = KITE_API_KEY,
        api_secret: str = KITE_API_SECRET,
        access_token: str = KITE_ACCESS_TOKEN,
    ) -> None:
        """Initialise the wrapper.

        Args:
            api_key:      Kite Connect API key.
            api_secret:   Kite Connect API secret.
            access_token: Pre-generated access token.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self._kite = None  # KiteConnect instance (lazy)
        logger.info("ZerodhaAPI initialised (stub mode).")

    # ── Authentication ───────────────────────

    def login(self, request_token: str = "") -> bool:
        """Authenticate with Kite Connect and obtain an access token.

        In production, exchange the ``request_token`` for a session
        token via the Kite Connect API.

        Args:
            request_token: Token received from Kite login redirect.

        Returns:
            ``True`` if authentication succeeded.
        """
        # ── STUB ──────────────────────────────
        # from kiteconnect import KiteConnect
        # self._kite = KiteConnect(api_key=self.api_key)
        # data = self._kite.generate_session(
        #     request_token, api_secret=self.api_secret
        # )
        # self.access_token = data["access_token"]
        # self._kite.set_access_token(self.access_token)
        # ──────────────────────────────────────
        logger.info("STUB: login called — returning success.")
        return True

    # ── Market Data ──────────────────────────

    def fetch_historical_data(
        self,
        instrument_token: int,
        from_date: str,
        to_date: str,
        interval: str = "day",
    ) -> pd.DataFrame:
        """Download historical OHLCV candles for an instrument.

        Args:
            instrument_token: Kite numeric instrument token.
            from_date:        Start date string ``'YYYY-MM-DD'``.
            to_date:          End date string ``'YYYY-MM-DD'``.
            interval:         Candle interval (``'minute'``, ``'day'``, etc.).

        Returns:
            A ``pandas.DataFrame`` with columns
            ``[date, open, high, low, close, volume]`` indexed by date.
        """
        # ── STUB ──────────────────────────────
        logger.info(
            "STUB: fetch_historical_data(%s, %s→%s, %s)",
            instrument_token, from_date, to_date, interval,
        )
        return pd.DataFrame(
            columns=["date", "open", "high", "low", "close", "volume"]
        )

    def get_ltp(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch the Last Traded Price for one or more instruments.

        Args:
            symbols: List of exchange-prefixed symbols, e.g.
                     ``["NSE:RELIANCE", "NSE:INFY"]``.

        Returns:
            A dict mapping each symbol to its LTP.
        """
        # ── STUB ──────────────────────────────
        logger.info("STUB: get_ltp(%s)", symbols)
        return {s: 0.0 for s in symbols}

    def get_quote(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch full market quotes for one or more instruments.

        Args:
            symbols: List of exchange-prefixed symbols.

        Returns:
            A dict mapping each symbol to its full quote dict.
        """
        # ── STUB ──────────────────────────────
        logger.info("STUB: get_quote(%s)", symbols)
        return {s: {} for s in symbols}

    # ── Order Management ─────────────────────

    def place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        price: float = 0.0,
        order_type: str = "MARKET",
        trigger_price: float = 0.0,
    ) -> OrderResponse:
        """Place a new order on Zerodha.

        Args:
            symbol:           NSE / BSE trading symbol.
            transaction_type: ``"BUY"`` or ``"SELL"``.
            quantity:         Number of shares.
            price:            Limit price (ignored for MARKET orders).
            order_type:       ``"MARKET"``, ``"LIMIT"``, ``"SL"``, ``"SL-M"``.
            trigger_price:    Trigger price for SL / SL-M orders.

        Returns:
            An :class:`OrderResponse` with order ID and status.
        """
        # ── STUB ──────────────────────────────
        logger.info(
            "STUB: place_order(%s %s × %d @ %s, type=%s)",
            transaction_type, symbol, quantity, price, order_type,
        )
        return OrderResponse(
            order_id="STUB_ORD_001",
            status="SUCCESS",
            message=f"Stub {transaction_type} order for {quantity} {symbol}",
        )

    def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        order_type: Optional[str] = None,
        trigger_price: Optional[float] = None,
    ) -> OrderResponse:
        """Modify an existing pending order.

        Args:
            order_id:      Broker order ID to modify.
            quantity:      New quantity (optional).
            price:         New limit price (optional).
            order_type:    New order type (optional).
            trigger_price: New trigger price (optional).

        Returns:
            An :class:`OrderResponse` confirming the modification.
        """
        # ── STUB ──────────────────────────────
        logger.info("STUB: modify_order(%s)", order_id)
        return OrderResponse(
            order_id=order_id, status="SUCCESS", message="Stub modify OK"
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel a pending order.

        Args:
            order_id: Broker order ID to cancel.

        Returns:
            An :class:`OrderResponse` confirming cancellation.
        """
        # ── STUB ──────────────────────────────
        logger.info("STUB: cancel_order(%s)", order_id)
        return OrderResponse(
            order_id=order_id, status="SUCCESS", message="Stub cancel OK"
        )

    # ── Portfolio ─────────────────────────────

    def get_positions(self) -> List[Dict[str, Any]]:
        """Retrieve current open positions.

        Returns:
            A list of position dicts (empty in stub mode).
        """
        # ── STUB ──────────────────────────────
        logger.info("STUB: get_positions()")
        return []

    def get_holdings(self) -> List[Dict[str, Any]]:
        """Retrieve current holdings (delivery / CNC stocks).

        Returns:
            A list of holding dicts.
        """
        # ── STUB ──────────────────────────────
        logger.info("STUB: get_holdings()")
        return []

    def get_order_history(self, order_id: str) -> List[Dict[str, Any]]:
        """Fetch the full modification history for an order.

        Args:
            order_id: Broker order ID.

        Returns:
            Chronological list of order-state snapshots.
        """
        # ── STUB ──────────────────────────────
        logger.info("STUB: get_order_history(%s)", order_id)
        return []

    # ── Funds ─────────────────────────────────

    def get_margins(self) -> Dict[str, Any]:
        """Fetch available margin / funds information.

        Returns:
            A dict with equity and commodity margin details.
        """
        # ── STUB ──────────────────────────────
        logger.info("STUB: get_margins()")
        return {"equity": {"available": 0.0}}


# ──────────────────────────────────────────────
# Free Market Data (Yahoo Finance)
# ──────────────────────────────────────────────


def get_ohlcv_free(symbol: str, days: int = 200) -> pd.DataFrame:
    """Fetch free historical OHLCV data from Yahoo Finance for NSE stocks.

    This is a **standalone helper** that does not require a Kite Connect
    session.  It automatically appends the ``.NS`` suffix so the caller
    can use plain NSE ticker names.

    Args:
        symbol: Plain NSE symbol name, e.g. ``"RELIANCE"``,
                ``"INFY"``, ``"HDFCBANK"``.  Do **not** include the
                ``.NS`` suffix — it is added automatically.
        days:   Number of calendar days of history to fetch
                (default ``200``).  Yahoo Finance may return fewer
                bars if the market was closed on some of those days.

    Returns:
        A ``pandas.DataFrame`` with a ``DatetimeIndex`` and lowercase
        columns: ``open``, ``high``, ``low``, ``close``, ``volume``.
        Rows with any ``NaN`` values are dropped.

    Raises:
        ValueError: If *symbol* is empty or *days* ≤ 0.
        Exception:  Propagates any network / Yahoo Finance errors.

    Example::

        >>> from broker.zerodha_api import get_ohlcv_free
        >>> df = get_ohlcv_free("RELIANCE", days=365)
        >>> print(df.tail())
    """
    if not symbol or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    if days <= 0:
        raise ValueError(f"days must be > 0, got {days}")

    symbol = symbol.strip().upper()
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        ticker = symbol
    else:
        ticker = f"{symbol}.NS"
    logger.info("Fetching %d days of OHLCV for %s via Yahoo Finance", days, ticker)

    df = yf.download(ticker, period=f"{days}d", interval="1d", auto_adjust=True)

    # Convert MultiIndex columns to single level if returned (yfinance >= 0.2.32)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })

    # Keep only the standard OHLCV columns (yfinance may add extras)
    df = df[["open", "high", "low", "close", "volume"]]
    df.dropna(inplace=True)

    logger.info("Fetched %d bars for %s", len(df), ticker)
    return df
