import threading
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple


@dataclass
class DeribitBinarySnapshot:
    """Snapshot of interpolated binary option data from Deribit"""
    lower_symbol: str
    upper_symbol: str
    target_strike: float
    asof: float
    lower_strike: float
    upper_strike: float
    lower_price: float
    upper_price: float
    target_price: float


class DeribitDatastream:
    """
    Deribit datastream that polls option instruments and computes interpolated binary prices.

    Polls four Deribit option instruments (2 strikes x 2 expirations), computes each
    option's binary price, then performs two-step linear interpolation:
    1. Interpolate between strikes for each expiration to get target strike price
    2. Interpolate between expirations to get final target price

    Similar interface to LimitlessDatastream but for Deribit binary option data.
    """

    def __init__(
        self,
        lower_instrument_earlier: str,
        upper_instrument_earlier: str,
        lower_instrument_later: str,
        upper_instrument_later: str,
        target_strike: float,
        poll_interval: float = 2.0,
        testnet: bool = False,
        timeout: int = 10
    ):
        self.lower_instrument_earlier = lower_instrument_earlier
        self.upper_instrument_earlier = upper_instrument_earlier
        self.lower_instrument_later = lower_instrument_later
        self.upper_instrument_later = upper_instrument_later
        self.target_strike = float(target_strike)

        self._interval = max(0.5, float(poll_interval))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_snapshot: Optional[DeribitBinarySnapshot] = None

        # Import here to avoid circular imports and handle missing dependencies
        try:
            from utils.deribit_option_params import DeribitOptionParams
            self._fetcher = DeribitOptionParams(testnet=testnet, timeout=timeout)
        except ImportError as e:
            raise ImportError(f"Failed to import DeribitOptionParams: {e}")

        # Current prices (similar to LimitlessDatastream's BBA tracking)
        self.lower_strike: Optional[float] = None
        self.upper_strike: Optional[float] = None
        self.lower_price: Optional[float] = None
        self.upper_price: Optional[float] = None
        self.target_price: Optional[float] = None
        self.last_update: Optional[float] = None

    def start(self) -> None:
        """Start the polling thread"""
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the polling thread"""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _update_prices(self) -> None:
        """Update internal price state (similar to LimitlessDatastream._update_bba)"""
        snapshot = self._fetch_snapshot()
        if snapshot:
            self._last_snapshot = snapshot
            self.lower_strike = snapshot.lower_strike
            self.upper_strike = snapshot.upper_strike
            self.lower_price = snapshot.lower_price
            self.upper_price = snapshot.upper_price
            self.target_price = snapshot.target_price
            self.last_update = snapshot.asof

    def get_snapshot(self) -> Optional[DeribitBinarySnapshot]:
        """Get current binary option snapshot (similar to LimitlessDatastream.get_bba)"""
        self._update_prices()
        return self._last_snapshot

    def get_target_price(self) -> Optional[float]:
        """Get the current interpolated target price"""
        self._update_prices()
        return self.target_price

    def _run(self) -> None:
        """Main polling loop"""
        while not self._stop.is_set():
            try:
                self._update_prices()
            except Exception:
                pass  # Continue polling on errors
            finally:
                self._stop.wait(self._interval)

    def _fetch_snapshot(self) -> Optional[DeribitBinarySnapshot]:
        """Fetch and compute interpolated binary option snapshot"""
        now = time.time()

        # Fetch all 4 instruments
        lower_earlier_params = self._fetch_params(self.lower_instrument_earlier)
        upper_earlier_params = self._fetch_params(self.upper_instrument_earlier)
        lower_later_params = self._fetch_params(self.lower_instrument_later)
        upper_later_params = self._fetch_params(self.upper_instrument_later)

        # Ensure all params were fetched successfully
        if None in (lower_earlier_params, upper_earlier_params, lower_later_params, upper_later_params):
            return None

        # Type narrowing - we know these are not None now
        assert lower_earlier_params is not None
        assert upper_earlier_params is not None
        assert lower_later_params is not None
        assert upper_later_params is not None

        # Extract binary prices for all 4 instruments
        binary_prices = [
            self._compute_binary_price(lower_earlier_params),
            self._compute_binary_price(upper_earlier_params),
            self._compute_binary_price(lower_later_params),
            self._compute_binary_price(upper_later_params)
        ]

        # Check if any binary price computation failed
        if any(result[0] is None or result[1] is None for result in binary_prices):
            return None

        # Extract values (we know they're not None due to check above)
        k_lower_earlier, p_lower_earlier = binary_prices[0]
        k_upper_earlier, p_upper_earlier = binary_prices[1]
        k_lower_later, p_lower_later = binary_prices[2]
        k_upper_later, p_upper_later = binary_prices[3]

        # Type narrowing for all extracted values
        if None in (k_lower_earlier, p_lower_earlier, k_upper_earlier, p_upper_earlier,
                   k_lower_later, p_lower_later, k_upper_later, p_upper_later):
            return None

        # Now we can safely assert these are floats
        assert isinstance(k_lower_earlier, float) and isinstance(p_lower_earlier, float)
        assert isinstance(k_upper_earlier, float) and isinstance(p_upper_earlier, float)
        assert isinstance(k_lower_later, float) and isinstance(p_lower_later, float)
        assert isinstance(k_upper_later, float) and isinstance(p_upper_later, float)

        # Step 1: Interpolate between strikes for each expiration
        price_earlier = self._interpolate_strike_price(
            k_lower_earlier, p_lower_earlier, k_upper_earlier, p_upper_earlier
        )
        price_later = self._interpolate_strike_price(
            k_lower_later, p_lower_later, k_upper_later, p_upper_later
        )

        # Step 2: Get time to expiration for both dates
        t_earlier = self._safe_get_float(lower_earlier_params, "T", 0.0)
        t_later = self._safe_get_float(lower_later_params, "T", 0.0)

        # Interpolate between expiration times
        final_price = self._interpolate_time_price(
            price_earlier, price_later, t_earlier, t_later
        )

        return DeribitBinarySnapshot(
            lower_symbol=self.lower_instrument_earlier,
            upper_symbol=self.upper_instrument_earlier,
            target_strike=self.target_strike,
            asof=now,
            lower_strike=k_lower_earlier,
            upper_strike=k_upper_earlier,
            lower_price=p_lower_earlier,
            upper_price=p_upper_earlier,
            target_price=final_price,
        )

    def _interpolate_strike_price(
        self,
        k_lower: float,
        p_lower: float,
        k_upper: float,
        p_upper: float
    ) -> float:
        """Interpolate price between two strikes for target strike"""
        if k_lower == k_upper:
            return (p_lower + p_upper) / 2

        slope = (p_upper - p_lower) / (k_upper - k_lower)
        return p_lower + slope * (self.target_strike - k_lower)

    def _interpolate_time_price(
        self,
        price_earlier: float,
        price_later: float,
        t_earlier: float,
        t_later: float
    ) -> float:
        """Interpolate price between two expiration times"""
        if t_earlier == t_later:
            return (price_earlier + price_later) / 2

        target_time = (t_earlier + t_later) / 2
        time_slope = (price_later - price_earlier) / (t_later - t_earlier)
        return price_earlier + time_slope * (target_time - t_earlier)

    def _safe_get_float(self, params: Optional[Dict[str, Any]], key: str, default: float) -> float:
        """Safely extract float value from params dictionary"""
        if params is None:
            return default
        try:
            value = params.get(key, default)
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    def _fetch_params(self, instrument: str) -> Optional[Dict[str, Any]]:
        """Fetch option parameters for an instrument"""
        try:
            return self._fetcher.get_params(instrument, r=0.05)
        except Exception:
            return None

    @staticmethod
    def _compute_binary_price(params: Optional[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
        """Compute binary option price from option parameters"""
        if params is None:
            return None, None

        try:
            # Import here to avoid potential circular imports
            from utils.implied_volatility import find_implied_volatility
            from utils.create_binary_prices import binary_option_price

            S = params.get("S")
            K = params.get("K")
            T = params.get("T")
            r = params.get("r")
            market_price = params.get("market_price")

            # Type safety checks - ensure all values are present
            if None in (S, K, T, r, market_price):
                return None, None

            # Convert to float with proper error handling
            try:
                S_float = float(S) if S is not None else 0.0
                K_float = float(K) if K is not None else 0.0
                T_float = float(T) if T is not None else 0.0
                r_float = float(r) if r is not None else 0.0
                market_price_float = float(market_price) if market_price is not None else 0.0
            except (ValueError, TypeError):
                return None, None

            try:
                iv = find_implied_volatility(S_float, K_float, T_float, r_float, market_price_float)
                price = binary_option_price(S_float, K_float, T_float, r_float, iv)
            except (ValueError, Exception):
                # Fallback for when IV calculation fails (often near expiry)
                if S_float > K_float:
                    price = 0.99  # Very close to 1 but not exactly 1
                else:
                    price = 0.01  # Very close to 0 but not exactly 0

            return K_float, float(price)
        except Exception:
            return None, None
