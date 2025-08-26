# deribit_option_params.py
import datetime as dt
import math
from typing import Any, Dict, Optional

import requests


class DeribitOptionParams:
    """
    Fetch S, K, T, r, and market_price for a Deribit option contract (no websockets).

    Usage:
        fetcher = DeribitOptionParams(testnet=False, timeout=10)
        params = fetcher.get_params("BTC-15AUG25-60000-C", r=0.05)
        # -> dict with S, K, T, r, market_price, expiry, asof (mirrors your Alpaca shape)
    """

    MAINNET = "https://www.deribit.com/api/v2"
    TESTNET = "https://test.deribit.com/api/v2"

    def __init__(self, testnet: bool = False, timeout: int = 10):
        self.base = self.TESTNET if testnet else self.MAINNET
        self.timeout = timeout
        self._next_id = 0
        self._session = requests.Session()

    # ---------- Public ----------

    def get_params(self, instrument: str, r: float = 0.05) -> Dict[str, Any]:
        ins = self._rpc("public/get_instrument", {"instrument_name": instrument})
        strike = float(ins.get("strike", ins.get("strike_price", 0.0)))
        expiry_ms = int(ins["expiration_timestamp"])
        expiry_dt = dt.datetime.fromtimestamp(expiry_ms / 1000.0, tz=dt.timezone.utc)
        expiry_str = expiry_dt.strftime("%Y-%m-%d")
        underlying = instrument.split("-", 1)[0] if "-" in instrument else ins.get("base_currency", "")

        tick = self._rpc("public/ticker", {"instrument_name": instrument})

        S = self._to_float_safe(tick.get("underlying_price")) or self._to_float_safe(tick.get("index_price"))
        if S is None:
            raise RuntimeError(f"Missing underlying/index price in ticker for {instrument}: {tick}")

        index_usd = self._to_float_safe(tick.get("index_price"))

        # Prefer mark -> mid -> last
        market_price_coin = (
            self._to_float_safe(tick.get("mark_price"))
            or self._mid_from_ticker(tick)
            or self._to_float_safe(tick.get("last_price"))
            or self._mid_from_order_book(instrument)
        )
        if market_price_coin is None:
            raise RuntimeError(f"Could not determine market_price for {instrument}")

        # Convert coin-denominated option price to USD if possible
        market_price_usd = market_price_coin * index_usd if index_usd is not None else None

        now_utc = dt.datetime.now(dt.timezone.utc)
        T = max((expiry_dt - now_utc).total_seconds(), 0.0) / (365.0 * 24 * 3600.0)

        return {
            "symbol": instrument,
            "underlying": underlying,
            "S": float(S),
            "K": float(strike),
            "T": float(T),
            "r": float(r),
            "market_price_coin": float(market_price_coin),
            "market_price": float(market_price_usd) if market_price_usd is not None else None,
            "expiry": expiry_str,
            "asof": now_utc.isoformat(),
        }

    # ---------- Internals ----------

    def _mid_from_ticker(self, tick: Dict[str, Any]) -> Optional[float]:
        bb = self._to_float_safe(tick.get("best_bid_price"))
        ba = self._to_float_safe(tick.get("best_ask_price"))
        if bb is not None and ba is not None and ba >= bb:
            return (bb + ba) / 2.0
        return None

    def _mid_from_order_book(self, instrument: str) -> Optional[float]:
        """
        Final fallback: request top of book and compute mid if both sides exist.
        """
        ob = self._rpc("public/get_order_book", {"instrument_name": instrument, "depth": 1})
        bb = self._to_float_safe(ob.get("best_bid_price"))
        ba = self._to_float_safe(ob.get("best_ask_price"))
        if bb is not None and ba is not None and ba >= bb:
            return (bb + ba) / 2.0
        return None

    def _rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Minimal JSON-RPC 2.0 over HTTP POST to Deribit public methods.
        Raises with helpful context on error.
        """
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        try:
            resp = self._session.post(self.base, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.HTTPError as e:
            body = ""
            try:
                body = f" | body: {resp.text}" # pyright: ignore
            except Exception:
                pass
            raise RuntimeError(f"HTTP error during {method}: {e}{body}") from None

        data = resp.json()
        if "error" in data and data["error"]:
            raise RuntimeError(f"RPC error for {method}: {data['error']}")
        result = data.get("result")
        if result is None:
            raise RuntimeError(f"No result for {method}: {data}")
        return result

    @staticmethod
    def _to_float_safe(x: Any) -> Optional[float]:
        try:
            if x is None:
                return None
            f = float(x)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except Exception:
            return None
