# deribit_binary_stream.py
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from deribit_data_retriver import DeribitOptionParams  # your class
from implied_volatility import find_implied_volatility  # your function
from create_binary_prices import binary_option_price    # your function


@dataclass
class BinaryInterpSnapshot:
    # Raw params
    lower_symbol: str
    upper_symbol: str
    target_strike: float
    asof: float

    # Per-leg prices (binary) and strikes
    lower_strike: float
    upper_strike: float
    lower_price: float
    upper_price: float

    # Interpolated target price
    target_price: float


class DeribitBinaryInterpStream:
    """
    Polls four Deribit option instruments (2 strikes x 2 expirations), computes each
    option's binary price, then performs two-step linear interpolation:
    1. Interpolate between strikes for each expiration to get target strike price
    2. Interpolate between expirations to get final target price

    Calls on_update(BinaryInterpSnapshot) when values change.

    - Uses your DeribitOptionParams.get_params() to fetch {S,K,T,r,market_price}
    - Uses your find_implied_volatility() + binary_option_price()
    """

    def __init__(
        self,
        lower_instrument_earlier: str,
        upper_instrument_earlier: str,
        lower_instrument_later: str,
        upper_instrument_later: str,
        target_strike: float,
        on_update: Optional[Callable[[BinaryInterpSnapshot], None]] = None,
        poll_interval: float = 2.0,
        testnet: bool = False,
        timeout: int = 10,
    ):
        self.lower_instrument_earlier = lower_instrument_earlier
        self.upper_instrument_earlier = upper_instrument_earlier
        self.lower_instrument_later = lower_instrument_later
        self.upper_instrument_later = upper_instrument_later
        self.target_strike = float(target_strike)

        self._on_update = on_update
        self._interval = max(0.5, float(poll_interval))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last: Optional[BinaryInterpSnapshot] = None

        self._fetcher = DeribitOptionParams(testnet=testnet, timeout=timeout)

    # ---- lifecycle ----
    def start(self):
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def latest(self) -> Optional[BinaryInterpSnapshot]:
        return self._last

    # ---- internals ----
    def _run(self):
        while not self._stop.is_set():
            try:
                snap = self._fetch_once()
                if snap and self._changed(self._last, snap):
                    self._last = snap
                    if self._on_update:
                        self._on_update(snap)
            except Exception:
                pass
            finally:
                self._stop.wait(self._interval)

    def _fetch_once(self) -> Optional[BinaryInterpSnapshot]:
        now = time.time()

        # Fetch all 4 instruments
        lower_earlier_params = self._fetch_params(self.lower_instrument_earlier)
        upper_earlier_params = self._fetch_params(self.upper_instrument_earlier)
        lower_later_params = self._fetch_params(self.lower_instrument_later)
        upper_later_params = self._fetch_params(self.upper_instrument_later)

        if None in (lower_earlier_params, upper_earlier_params, lower_later_params, upper_later_params):
            return None

        # Extract binary prices for all 4 instruments
        k_lower_earlier, p_lower_earlier = self._binary_price(lower_earlier_params)
        k_upper_earlier, p_upper_earlier = self._binary_price(upper_earlier_params)
        k_lower_later, p_lower_later = self._binary_price(lower_later_params)
        k_upper_later, p_upper_later = self._binary_price(upper_later_params)

        if None in (k_lower_earlier, p_lower_earlier, k_upper_earlier, p_upper_earlier,
                   k_lower_later, p_lower_later, k_upper_later, p_upper_later):
            return None

        # Step 1: Interpolate between strikes for each expiration
        # Handle case where strikes are the same (no interpolation needed)
        if k_lower_earlier == k_upper_earlier:
            # Same strikes for earlier expiration - use average price or pick one
            price_earlier = (p_lower_earlier + p_upper_earlier) / 2
        else:
            # Different strikes - interpolate
            slope_earlier = (p_upper_earlier - p_lower_earlier) / (k_upper_earlier - k_lower_earlier)
            price_earlier = p_lower_earlier + slope_earlier * (self.target_strike - k_lower_earlier)

        if k_lower_later == k_upper_later:
            # Same strikes for later expiration - use average price or pick one
            price_later = (p_lower_later + p_upper_later) / 2
        else:
            # Different strikes - interpolate
            slope_later = (p_upper_later - p_lower_later) / (k_upper_later - k_lower_later)
            price_later = p_lower_later + slope_later * (self.target_strike - k_lower_later)

        # Step 2: Get time to expiration for both dates
        t_earlier = float(lower_earlier_params.get("T", 0))
        t_later = float(lower_later_params.get("T", 0))

        # Handle case where expiration times are the same (no interpolation needed)
        if t_earlier == t_later:
            # Same expiration times - use average price
            final_price = (price_earlier + price_later) / 2
        else:
            # Different expiration times - interpolate to midpoint between the two
            target_time = (t_earlier + t_later) / 2
            time_slope = (price_later - price_earlier) / (t_later - t_earlier)
            final_price = price_earlier + time_slope * (target_time - t_earlier)

        return BinaryInterpSnapshot(
            lower_symbol=self.lower_instrument_earlier,
            upper_symbol=self.upper_instrument_earlier,
            target_strike=self.target_strike,
            asof=now,
            lower_strike=float(k_lower_earlier),
            upper_strike=float(k_upper_earlier),
            lower_price=float(p_lower_earlier),
            upper_price=float(p_upper_earlier),
            target_price=float(final_price),
        )

    def _fetch_params(self, instrument: str):
        try:
            return self._fetcher.get_params(instrument, r=0.05)
        except Exception:
            return None

    @staticmethod
    def _binary_price(params) -> tuple[Optional[float], Optional[float]]:
        try:
            S = float(params.get("S")); K = float(params.get("K"))
            T = float(params.get("T")); r = float(params.get("r"))
            market_price = float(params.get("market_price")) if params.get("market_price") is not None else None
            if None in (S, K, T, r, market_price):
                return None, None

            try:
                iv = find_implied_volatility(S, K, T, r, market_price)
                price = binary_option_price(S, K, T, r, iv)
            except (ValueError, Exception):
                # Fallback for when IV calculation fails (often near expiry)
                # For call options, binary price approaches 1 if S > K, 0 if S < K
                if S > K:
                    price = 0.99  # Very close to 1 but not exactly 1 to avoid numerical issues
                else:
                    price = 0.01  # Very close to 0 but not exactly 0

            return K, float(price)
        except Exception:
            return None, None

    @staticmethod
    def _changed(prev: Optional[BinaryInterpSnapshot], cur: BinaryInterpSnapshot) -> bool:
        if prev is None:
            return True
        return (
            prev.lower_price != cur.lower_price
            or prev.upper_price != cur.upper_price
            or prev.target_price != cur.target_price
        )
