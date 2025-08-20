"""
Limitless Exchange Order Manager (rewritten with working sell functionality)
- Robust auth with cookie reuse
- 429-aware backoff for /auth/signing-message
- EIP-712 signing compatible with eth-account >=0.8 and fallback
- Simple buy/sell helpers for YES/NO tokens
- Working sell functionality based on fixing_sell.py
- Added buy functionality with proper fee calculations
"""

from __future__ import annotations

import os
import time
import json
import random
import threading
import math
from decimal import Decimal
from typing import Optional, Tuple, Literal, Dict
import datetime
import sys
from snap import safe_snap_down

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

from dotenv import load_dotenv
load_dotenv()

def log(msg: str):
    """Simple timestamped logger."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stdout, flush=True)

# Debug gate (set LL_DEBUG=1 to enable deep logs)
DEBUG = os.getenv("LL_DEBUG", "0") not in ("0", "", "false", "False")

# --- Demo banner ---
print("⚠️  WARNING: This is an example trading script for educational purposes.")
print("⚠️  Limitless Labs is not responsible for any losses or mistakes.")
print("⚠️  Always test with small amounts first and understand the code.")
print("⚠️  USE AT YOUR OWN RISK.\n")

# --- EIP-712 compatibility layer ---
try:
    from eth_account.messages import encode_typed_data
    print("✅ encode_typed_data available")
    _HAS_NEW_TD = True
except ImportError:
    try:
        from eth_account.messages import encode_structured_data as encode_typed_data
        print("✅ Using encode_structured_data (fallback)")
        _HAS_NEW_TD = False
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Please: pip install 'eth-account>=0.8.0'")
        raise

def _string_to_hex(text: str) -> str:
    return "0x" + text.encode("utf-8").hex()

def _to_checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr)

# --- EIP-712 ORDER TYPES (from working fixing_sell.py) ---
ORDER_TYPES = {
    "Order": [
        {"name": "salt",         "type": "uint256"},
        {"name": "maker",        "type": "address"},
        {"name": "signer",       "type": "address"},
        {"name": "taker",        "type": "address"},
        {"name": "tokenId",      "type": "uint256"},
        {"name": "makerAmount",  "type": "uint256"},
        {"name": "takerAmount",  "type": "uint256"},
        {"name": "expiration",   "type": "uint256"},
        {"name": "nonce",        "type": "uint256"},
        {"name": "feeRateBps",   "type": "uint256"},
        {"name": "side",         "type": "uint8"},   # 0 = BUY, 1 = SELL
        {"name": "signatureType","type": "uint8"}
    ]
}

# --- Minimal ABIs for approvals ---
ERC1155_ABI = [
    {"constant": False, "inputs": [
        {"name": "operator", "type": "address"},
        {"name": "approved", "type": "bool"}],
     "name": "setApprovalForAll", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"constant": True, "inputs": [
        {"name": "account", "type": "address"},
        {"name": "operator", "type": "address"}],
     "name": "isApprovedForAll", "outputs": [{"name": "", "type": "bool"}],
     "stateMutability": "view", "type": "function"}
]

ERC165_ABI = [
    {"constant": True, "inputs": [{"name":"interfaceId","type":"bytes4"}],
     "name":"supportsInterface", "outputs":[{"name":"","type":"bool"}],
     "stateMutability":"view","type":"function"}
]

# --- Type definitions ---
Market = Literal["YES", "NO"]
Side = Literal["BUY", "SELL"]

class LimitlessOrderManager:
    def __init__(
        self,
        slug: str,
        yes_token_id: str,
        no_token_id: str,
        *,
        api_url: Optional[str] = None,
        clob_address: Optional[str] = None,
        negrisk_address: Optional[str] = None,
        ctf_erc1155_addr: Optional[str] = None,
        base_rpc: Optional[str] = None,
        operator_addrs: Optional[str] = None,
        private_key: Optional[str] = None,
        auth_ttl_sec: int = 15 * 60,
    ):
        # Config / env
        self.api_url = api_url or os.getenv("API_URL", "https://api.limitless.exchange")
        self.clob_address = _to_checksum(clob_address or os.getenv("CLOB_CFT_ADDR", "0xa4409D988CA2218d956BeEFD3874100F444f0DC3"))
        self.negrisk_address = _to_checksum(negrisk_address or os.getenv("NEGRISK_CFT_ADDR", "0x5a38afc17F7E97ad8d6C547ddb837E40B4aEDfC6"))
        self.ctf_erc1155_addr = _to_checksum(ctf_erc1155_addr or os.getenv("CTF_ERC1155_ADDR", "0xC9c98965297Bc527861c898329Ee280632B76e18"))
        self.base_rpc = base_rpc or os.getenv("BASE_RPC", "https://mainnet.base.org")
        self.private_key = private_key or os.getenv("PRIVATE_KEY")

        if not self.private_key:
            raise RuntimeError("PRIVATE_KEY not set")

        # Web3 setup for approvals
        self.w3 = Web3(Web3.HTTPProvider(self.base_rpc))
        self.ctf_contract = self.w3.eth.contract(address=self.ctf_erc1155_addr, abi=ERC1155_ABI)

        # Operator addresses for approvals
        operator_addrs_env = operator_addrs or os.getenv("OPERATOR_ADDRS", "").strip()
        if operator_addrs_env:
            self.operator_list = []
            for a in operator_addrs_env.split(","):
                a = a.strip()
                if a:
                    self.operator_list.append(_to_checksum(a))
        else:
            # Fallback: set OPERATOR_ADDRS properly for production
            self.operator_list = [self.clob_address, self.negrisk_address]

        # Market info
        self.slug = slug
        self.tokens = {"YES": str(yes_token_id), "NO": str(no_token_id)}

        # HTTP session with retries
        self.sess = requests.Session()
        self.sess.headers.update({"Accept": "application/json", "User-Agent": "limitless-ordermanager/2.0"})
        try:
            retry = Retry(
                total=3,
                backoff_factor=2,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET", "POST", "DELETE"]),
            )
            adapter = HTTPAdapter(max_retries=retry)
            self.sess.mount("https://", adapter)
            self.sess.mount("http://", adapter)
        except Exception:
            pass  # best-effort

        # Auth state
        self._session_cookie: Optional[str] = None
        self._auth_headers: Optional[dict] = None
        self._auth_expiry_ts: float = 0.0
        self._AUTH_TTL_SEC = auth_ttl_sec
        self._user_cached: Optional[dict] = None

        # Single-flight locks and throttles
        self._auth_lock = threading.Lock()
        self._signing_lock = threading.Lock()
        self._last_auth_ts: float = 0.0
        self._last_signing_ts: float = 0.0
        self._min_signing_interval = 1.0
        self._signing_message_cache: Optional[str] = None
        self._signing_message_ttl = 60.0  # reuse message briefly

        # Rate limiting for API calls
        self._last_fill_check: float = 0.0
        self._last_portfolio_fetch: float = 0.0
        self._cached_portfolio: dict = {}

        # Order State
        self.active_orders = []

        print("Auth user:", self._user_cached and self._user_cached.get("account"))
        print("Signer   :", Account.from_key(self.private_key).address)

    # ------------- Chain validation helpers --------------------------------
    def _require_base_chain(self):
        cid = self.w3.eth.chain_id
        if cid != 8453:
            raise RuntimeError("❌ Connected RPC is not Base mainnet (chainId 8453). Check BASE_RPC.")

    def _require_contract_at(self, addr: str):
        code = self.w3.eth.get_code(addr)
        if len(code) == 0:
            raise RuntimeError("❌ No contract deployed at this address on the connected RPC.")

    def _warn_if_not_erc1155(self, addr: str):
        try:
            c165 = self.w3.eth.contract(address=addr, abi=ERC165_ABI)
            is1155 = c165.functions.supportsInterface(b"\xd9\xb6\x7a\x26").call()
            if not is1155:
                pass  # Contract may not report ERC-1155 via ERC-165
        except Exception:
            pass  # ERC165 check failed, continuing

    # ------------- Public convenience methods --------------------------------
    def buy_yes(self, price_dollars: float, amount_usd: float):
        amount = safe_snap_down(amount_usd / price_dollars, 0.01)

        try:
            order = self._place(side="BUY", market="YES", price_dollars=price_dollars, amount=amount)
            self.active_orders.append(order['order']['id'])
            log(f"Placed a buy_yes order at {price_dollars} for {amount} USD")
            return order
        except Exception as e:
            log(f"Could not place buy_yes order: {e}")
            return None

    def buy_no(self, price_dollars: float, amount_usd: float):
        amount = safe_snap_down(amount_usd / price_dollars, 0.01)

        try:
            order = self._place(side="BUY", market="NO", price_dollars=price_dollars, amount=amount)
            self.active_orders.append(order['order']['id'])
            log(f"Placed a buy_no order at {price_dollars} for {amount} USD")
            return order
        except Exception as e:
            log(f"Could not place buy_no order: {e}")
            return None

    def sell_yes(self, price_dollars: float, amount_usd: float):
        portfolio = self.get_portfolio()

        amount = safe_snap_down(amount_usd / price_dollars, 0.01)


        try:
            order = self._place(side="SELL", market="YES", price_dollars=price_dollars, amount=amount)
            self.active_orders.append(order['order']['id'])
            log(f"Placed a sell_yes order at {price_dollars} for {amount} USD")
            return order
        except Exception as e:
            log(f"Could not place sell_yes order: {e}")
            return None

    def sell_no(self, price_dollars: float, amount_usd: float):
        amount = safe_snap_down(amount_usd / price_dollars, 0.01)

        try:
            order = self._place(side="SELL", market="NO", price_dollars=price_dollars, amount=amount)
            self.active_orders.append(order['order']['id'])
            log(f"Placed a sell_no order at {price_dollars} for {amount} USD")
            return order
        except Exception as e:
            log(f"Could not place sell_no order: {e}")
            return None

    # ---------- Public cancel APIs ----------
    def cancel_order(self, order_id: str) -> dict:
        """Cancel a single order by order_id."""
        headers = self._ensure_auth()
        res = self._delete_order(order_id, headers)
        try:
            self.active_orders = [oid for oid in self.active_orders if oid != order_id]
        except Exception:
            pass
        return res

    def cancel_orders(self, order_ids: list[str]) -> dict:
        """Cancel multiple orders with retries and verification."""
        if not order_ids:
            return {"ok": True, "canceled": [], "note": "no order ids provided"}

        max_attempts = 3
        for attempt in range(max_attempts):
            headers = self._ensure_auth()

            try:
                # Try batch cancel first
                res = self._cancel_batch(order_ids, headers)
                log(f"Batch cancel attempt {attempt + 1}: {res}")

                # Verify cancellation by checking each order
                verified_canceled = self._verify_orders_canceled(order_ids, headers)
                if verified_canceled:
                    self.active_orders = [oid for oid in self.active_orders if oid not in set(order_ids)]
                    return {"ok": True, "canceled": order_ids, "verified": True, "attempt": attempt + 1}

            except Exception as batch_err:
                log(f"Batch cancel failed on attempt {attempt + 1}: {batch_err}")

                # Fall back to individual cancellation
                try:
                    results = []
                    for oid in order_ids:
                        try:
                            result = self._delete_order(oid, headers)
                            results.append(result)
                            time.sleep(0.2)  # Small delay between individual cancels
                        except Exception as e:
                            log(f"Failed to cancel order {oid}: {e}")
                            results.append({"ok": False, "orderId": oid, "error": str(e)})

                    # Check if all individual cancels succeeded
                    all_ok = all(r.get("ok", False) for r in results)
                    if all_ok:
                        self.active_orders = [oid for oid in self.active_orders if oid not in set(order_ids)]
                        return {"ok": True, "canceled": order_ids, "method": "individual", "attempt": attempt + 1}

                except Exception as individual_err:
                    log(f"Individual cancel also failed on attempt {attempt + 1}: {individual_err}")

            # Wait before retry (except on last attempt)
            if attempt < max_attempts - 1:
                wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                log(f"Retrying cancel in {wait_time} seconds...")
                time.sleep(wait_time)

        # All attempts failed - force remove from active list and raise error
        log(f"❌ CRITICAL: Failed to cancel orders after {max_attempts} attempts: {order_ids}")
        self.active_orders = [oid for oid in self.active_orders if oid not in set(order_ids)]
        raise RuntimeError(f"Failed to cancel orders after {max_attempts} attempts: {order_ids}")

    def _verify_orders_canceled(self, order_ids: list[str], headers: dict) -> bool:
        """Verify that orders were actually canceled by checking their status"""
        for oid in order_ids:
            try:
                url = f"{self.api_url}/orders/{oid}"
                r = self.sess.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    # Order still exists - check if it's canceled
                    order_data = r.json()
                    status = order_data.get("status", "").lower()
                    if status not in ("canceled", "cancelled", "filled", "completed"):
                        log(f"Order {oid} still active with status: {status}")
                        return False
                # 404 means order is gone (canceled or filled), which is good
            except Exception as e:
                log(f"Could not verify order {oid} cancellation: {e}")
                return False
        return True

    def cancel_active_orders(self) -> dict:
        """Cancel all active orders with robust retry logic"""
        if not self.active_orders:
            return {"ok": True, "canceled": [], "note": "no active orders to cancel"}

        ids = list(self.active_orders)
        log(f"Attempting to cancel {len(ids)} active orders: {ids}")
        return self.cancel_orders(ids)

    def has_active_orders(self) -> bool:
        return bool(self.active_orders)

    def is_order_alone_on_level(self, order_id: str) -> Optional[bool]:
        return None

    def check_orders_filled(self) -> bool:
        """Check if any active orders have been filled - conservative approach with rate limiting"""
        if not self.active_orders:
            return False

        # Rate limit: only check every 60 seconds
        now = time.time()
        if not hasattr(self, '_last_fill_check') or (now - self._last_fill_check) < 60:
            return False

        self._last_fill_check = now

        headers = self._ensure_auth()
        filled_orders = []

        for order_id in self.active_orders[:]:  # Copy list to avoid modification during iteration
            try:
                url = f"{self.api_url}/orders/{order_id}"
                r = self.sess.get(url, headers=headers, timeout=10)

                if r.status_code == 200:
                    order_data = r.json()
                    status = order_data.get("status", "").lower()

                    # Only mark as filled if explicitly filled status
                    if status == "filled":
                        filled_orders.append(order_id)
                    # Or if remaining quantity is exactly 0 AND status is not "open"
                    elif order_data.get("remainingQuantity") == 0 and status != "open":
                        filled_orders.append(order_id)

                # Ignore 404s and other errors - don't assume filled
                # Add small delay between order checks
                time.sleep(0.5)
            except Exception:
                continue

        # Remove filled orders from active list
        if filled_orders:
            self.active_orders = [oid for oid in self.active_orders if oid not in filled_orders]
            return True

        return False

    def get_portfolio(self) -> dict:
        # Rate limit portfolio fetches to once per 90 seconds
        now = time.time()
        if hasattr(self, '_last_portfolio_fetch') and (now - self._last_portfolio_fetch) < 90:
            return getattr(self, '_cached_portfolio', {})

        self._last_portfolio_fetch = now

        headers = self._ensure_auth()
        user = self._user_cached or {}
        user_id = user.get("id")

        if not user_id:
            raise RuntimeError("No user ID available for portfolio fetch")

        # Try only the most likely endpoints first
        endpoints_to_try = [
            "/portfolio/positions",
            f"/users/{user_id}/portfolio",
            f"/portfolio",
        ]

        for endpoint in endpoints_to_try:
            url = f"{self.api_url}{endpoint}"
            try:
                r = self.sess.get(url, headers=headers, timeout=20)
                if r.status_code == 200:
                    portfolio = r.json()
                    self._cached_portfolio = portfolio  # Cache the result
                    return portfolio
                elif r.status_code == 401:
                    try:
                        headers = self._ensure_auth(force_refresh=True)
                        r = self.sess.get(url, headers=headers, timeout=20)
                        if r.status_code == 200:
                            portfolio = r.json()
                            self._cached_portfolio = portfolio
                            return portfolio
                    except Exception:
                        pass
                elif r.status_code == 404:
                    continue
                else:
                    continue
            except requests.RequestException:
                continue

        # Return cached portfolio if all endpoints fail
        return getattr(self, '_cached_portfolio', {})

    # ------------- Approval management for SELL orders ----------------------
    def ensure_ctf_sell_approval(self, owner: str):
        """Ensure ERC-1155 setApprovalForAll on CTF for sell operations."""
        owner = _to_checksum(owner)
        self._require_base_chain()
        self._require_contract_at(self.ctf_erc1155_addr)
        self._warn_if_not_erc1155(self.ctf_erc1155_addr)

        pk = self.private_key if self.private_key.startswith("0x") else "0x" + self.private_key
        acct = Account.from_key(pk)
        if acct.address.lower() != owner.lower():
            raise ValueError("Owner and signer mismatch for approval tx")

        for operator in self.operator_list:
            try:
                already = self.ctf_contract.functions.isApprovedForAll(owner, operator).call({"from": owner})
            except Exception as e:
                pass  # isApprovedForAll view failed, continuing
                already = False

            if already:
                pass  # Already approved
                continue

            try:
                gas_est = self.ctf_contract.functions.setApprovalForAll(operator, True).estimate_gas({"from": owner})
            except Exception as eg:
                raise RuntimeError(f"❌ setApprovalForAll would revert for operator {operator}: {eg}")

            tx = self.ctf_contract.functions.setApprovalForAll(operator, True).build_transaction({
                "from": owner,
                "nonce": self.w3.eth.get_transaction_count(owner),
                "maxFeePerGas": self.w3.to_wei("0.5", "gwei"),
                "maxPriorityFeePerGas": self.w3.to_wei("0.1", "gwei"),
                "gas": int(gas_est * 1.2),
                "chainId": 8453,
            })
            signed = self.w3.eth.account.sign_transaction(tx, pk)
            tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
            rcpt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if rcpt.status != 1:
                raise RuntimeError(f"❌ setApprovalForAll failed on-chain for operator {operator}")

    # ------------- Core flow ---------------------------------------------------
    def _place(self, *, side: Side, market: Market, price_dollars: float, amount: float) -> dict:
        """Simple order placement - you can customize this method"""
        print(f"[DEBUG] _place called with side={side}, market={market}, price_dollars={price_dollars}, amount={amount}")

        headers = self._ensure_auth()
        user = self._user_cached or {}

        # For sell orders, ensure approvals are in place
        if side == "SELL":
            self.ensure_ctf_sell_approval(user.get("account"))

        maker_addr = user.get("account")
        if not maker_addr:
            raise RuntimeError("No account address available from auth")

        fee_bps = int(user.get("rank", {}).get("feeRateBps", 0))
        owner_id = user.get("id")
        token_id = self.tokens[market]

        # Amount calculation - amount_usd is the USD value to trade
        scaling_factor = 1_000_000  # USDC uses 6 decimals
        price = price_dollars

        if side == "BUY":
            # For BUY: calculate exact amounts expected by server
            # amount_usd represents the number of shares (contracts / scaling_factor)
            shares = int(amount)
            contracts_amount = shares * scaling_factor
            # Use exact decimal calculation to avoid rounding errors
            collateral_amount = int(Decimal(str(price)) * Decimal(contracts_amount))

            # Ensure proper USDC scaling (6 decimals)
            maker_amount = int(collateral_amount)    # BUY: maker = USDC collateral (6 decimals)
            taker_amount = int(contracts_amount)     # BUY: taker = contracts (6 decimals)
            side_flag = 0

            print(f"[DEBUG] BUY: shares={shares}, contracts_amount={contracts_amount}")
            print(f"[DEBUG] BUY: collateral_amount={collateral_amount}")
            print(f"[DEBUG] BUY: maker_amount={maker_amount}, taker_amount={taker_amount}")
        else:
            # SELL: Use exact logic from execute_trade in fixing_sell.py
            shares = int(amount)
            fee = fee_bps / 10_000.0

            print(f"[DEBUG] SELL: shares={shares}, fee={fee} (from fee_bps={fee_bps})")

            # SELL invariant with fee:
            # makerAmount = contracts_after_fee (6 decimals)
            # takerAmount = floor(price * contracts_after_fee) (6 decimal USDC)
            contracts_pre = shares * scaling_factor
            print(f"[DEBUG] SELL: contracts_pre={contracts_pre}")

            contracts_after = math.floor(contracts_pre * (1.0 - fee))
            print(f"[DEBUG] SELL: contracts_after={contracts_after} (after fee calc: {contracts_pre} * {1.0 - fee})")

            # Let's also check what the exact calculation would be without floor
            contracts_after_exact = contracts_pre * (1.0 - fee)
            print(f"[DEBUG] SELL: contracts_after_exact (before floor)={contracts_after_exact}")

            collateral_amount = math.floor(price * contracts_after)
            print(f"[DEBUG] SELL: collateral_amount={collateral_amount} (from {price} * {contracts_after})")

            # Let's also check what the exact calculation would be without floor
            collateral_amount_exact = price * contracts_after
            print(f"[DEBUG] SELL: collateral_amount_exact (before floor)={collateral_amount_exact}")

            # Ensure proper scaling for USDC (6 decimals)
            maker_amount = int(contracts_after)      # SELL: maker = contracts (6 decimals)
            taker_amount = int(collateral_amount)    # SELL: taker = USDC collateral (6 decimals)
            side_flag = 1

            print(f"[DEBUG] SELL: maker_amount={maker_amount}, taker_amount={taker_amount}")

            # Let's calculate what the server expects based on the error message
            expected_collateral = 48383600
            expected_contracts = 281300000
            actual_collateral = taker_amount
            actual_contracts = maker_amount


        # Build and sign order
        unsigned_order = self._create_order_payload_without_signature(
            maker_addr, token_id, maker_amount, taker_amount, fee_bps, side_flag
        )

        signature = self._create_signature_for_order_payload(unsigned_order)

        final_order_payload = {
            "order": { **unsigned_order, "price": float(price), "signature": signature },
            "ownerId": owner_id,
            "orderType": "GTC",
            "marketSlug": self.slug,
        }

        return self._create_order_api(final_order_payload, headers)

    # ------------- Auth helpers (same as before) ------------------------------
    def _ensure_auth(self, force_refresh: bool = False) -> dict:
        now = time.time()
        if not force_refresh and self._auth_headers and self._session_cookie and now < self._auth_expiry_ts:
            return self._auth_headers

        with self._auth_lock:
            now = time.time()
            if not force_refresh and self._auth_headers and self._session_cookie and now < self._auth_expiry_ts:
                return self._auth_headers

            since_last = now - self._last_auth_ts
            if since_last < 1.0:
                time.sleep(1.0 - since_last + random.uniform(0, 0.25))

            signing_message = self._get_signing_message()

            max_attempts = 5
            delay = 0.5
            last_err = None
            for _ in range(max_attempts):
                try:
                    session_cookie, user = self._login(self.private_key, signing_message)
                    headers = {
                        "cookie": f"limitless_session={session_cookie}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    }
                    self._session_cookie = session_cookie
                    self._auth_headers = headers
                    self._auth_expiry_ts = time.time() + self._AUTH_TTL_SEC
                    self._user_cached = user
                    self._last_auth_ts = time.time()
                    return headers
                except RuntimeError as e:
                    msg = str(e)
                    last_err = e
                    if "429" in msg:
                        sleep_for = delay + random.uniform(0, 0.25)
                        time.sleep(sleep_for)
                        delay = min(delay * 2, 8.0)
                    else:
                        time.sleep(delay)
                        delay = min(delay * 2, 4.0)
            raise last_err or RuntimeError("Authentication failed after retries")

    def _get_signing_message(self) -> str:
        """Get signing message with rate limiting and caching"""
        now = time.time()
        if self._signing_message_cache and (now - self._last_signing_ts) < self._signing_message_ttl:
            return self._signing_message_cache

        with self._signing_lock:
            now = time.time()
            if self._signing_message_cache and (now - self._last_signing_ts) < self._signing_message_ttl:
                return self._signing_message_cache

            since_last = now - self._last_signing_ts
            if since_last < self._min_signing_interval:
                time.sleep(self._min_signing_interval - since_last + random.uniform(0, 0.1))

            url = f"{self.api_url}/auth/signing-message"
            max_attempts = 6
            delay = 0.3
            for attempt in range(1, max_attempts + 1):
                try:
                    r = self.sess.get(url, timeout=10)
                    if r.status_code == 200:
                        msg = r.text
                        self._signing_message_cache = msg
                        self._last_signing_ts = time.time()
                        return msg

                    if r.status_code == 429:
                        ra = r.headers.get("Retry-After")
                        sleep_for = float(ra) if ra else delay
                        time.sleep(sleep_for + random.uniform(0, 0.25))
                        delay = min(delay * 2, 8.0)
                        continue

                    if r.status_code in (500, 502, 503, 504):
                        time.sleep(delay + random.uniform(0, 0.25))
                        delay = min(delay * 2, 4.0)
                        continue

                    raise Exception(f"Failed to get signing message: {r.status_code} {r.text}")

                except requests.RequestException as e:
                    time.sleep(delay + random.uniform(0, 0.25))
                    delay = min(delay * 2, 4.0)

            raise Exception("Failed to get signing message after retries")

    def _login(self, private_key: str, signing_message: str) -> Tuple[str, dict]:
        """Login using signing message (from fixing_sell.py)"""
        account = Account.from_key(private_key)
        address = account.address
        message = encode_defunct(text=signing_message)
        signature = account.sign_message(message)

        headers = {
            "x-account": address,
            "x-signing-message": _string_to_hex(signing_message),
            "x-signature": signature.signature.hex() if signature.signature.hex().startswith("0x") else "0x" + signature.signature.hex(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        r = requests.post(f"{self.api_url}/auth/login", headers=headers, json={"client":"eoa"}, timeout=20)
        if r.status_code == 200:
            return r.cookies.get("limitless_session"), r.json()
        raise Exception(f"Authentication failed: {r.status_code} - {r.text}")

    # ---------- Low-level cancel helpers ----------
    def _delete_order(self, order_id: str, headers: dict) -> dict:
        url = f"{self.api_url}/orders/{order_id}"
        r = self.sess.delete(url, headers=headers, timeout=30)
        if r.status_code in (200, 202, 204):
            payload = {"ok": True, "orderId": order_id, "status": r.status_code}
            try:
                payload.update(r.json())
            except Exception:
                pass
            return payload

        url2 = f"{self.api_url}/orders/{order_id}/cancel"
        r2 = self.sess.post(url2, headers=headers, timeout=30)
        if r2.status_code in (200, 202):
            payload = {"ok": True, "orderId": order_id, "status": r2.status_code}
            try:
                payload.update(r2.json())
            except Exception:
                pass
            return payload

        raise RuntimeError(f"Cancel failed for {order_id}: {r.status_code} {r.text} | {r2.status_code} {r2.text}")

    def _cancel_batch(self, order_ids: list[str], headers: dict) -> dict:

        print('ORDER_IDS:', order_ids, 'HEADERS:', headers)
        url = f"{self.api_url}/orders/cancel-batch"

        body = {"orderIds": order_ids}
        print('BODY:', body)
        r = self.sess.post(url, headers=headers, json=body, timeout=45)
        if r.status_code in (200, 202):
            try:
                data = r.json()
            except Exception:
                data = {}
            data.setdefault("ok", True)
            if "canceled" not in data:
                data["canceled"] = order_ids
            return data

        if r.status_code in (400, 404):
            alt_body = {"ids": order_ids}
            r2 = self.sess.post(url, headers=headers, json=alt_body, timeout=45)
            if r2.status_code in (200, 202):
                try:
                    data = r2.json()
                except Exception:
                    data = {}
                data.setdefault("ok", True)
                if "canceled" not in data:
                    data["canceled"] = order_ids
                data["note"] = "used alternate body schema"
                return data

        raise RuntimeError(f"Batch cancel failed {r.status_code}: {r.text}")

    # ------------- Order building and signing (from fixing_sell.py) -----------
    def _get_eip712_domain(self):
        """EIP-712 domain (from fixing_sell.py)"""
        return {
            "name": "Limitless CTF Exchange",
            "version": "1",
            "chainId": 8453,
            "verifyingContract": self.clob_address,
        }

    def _create_order_payload_without_signature(self, maker_address, token_id, maker_amount, taker_amount, fee_rate_bps, side_flag):
        """Create unsigned order payload (from fixing_sell.py)"""
        salt = int(time.time() * 1000) + (24 * 60 * 60 * 1000)  # now + 24h (ms)
        return {
            "salt":         salt,
            "maker":        maker_address,
            "signer":       maker_address,
            "taker":        "0x0000000000000000000000000000000000000000",  # open
            "tokenId":      str(token_id),  # string for API
            "makerAmount":  maker_amount,
            "takerAmount":  taker_amount,
            "expiration":   "0",            # no expiry
            "nonce":        0,
            "feeRateBps":   fee_rate_bps,
            "side":         side_flag,      # 0 = BUY, 1 = SELL
            "signatureType": 0,             # 0 = EOA
        }

    def _create_signature_for_order_payload(self, order_payload) -> str:
        """Create EIP-712 signature for order (from fixing_sell.py)"""
        msg = dict(order_payload)
        msg["tokenId"]    = int(msg["tokenId"])
        msg["expiration"] = int(msg["expiration"])

        domain = self._get_eip712_domain()

        try:
            encoded = encode_typed_data(
                domain_data=domain,
                message_types=ORDER_TYPES,
                message_data=msg,
            )
        except Exception:
            encoded = encode_typed_data({
                "types": ORDER_TYPES,
                "primaryType": "Order",
                "domain": domain,
                "message": msg,
            })

        acct = Account.from_key(self.private_key if self.private_key.startswith("0x") else "0x"+self.private_key)
        signed = acct.sign_message(encoded)
        sig = signed.signature.hex()
        return sig

    def _create_order_api(self, order_payload, headers):
        """Submit order to API"""
        api_url = f"{self.api_url}/orders"
        r = requests.post(api_url, headers=headers, json=order_payload, timeout=35)
        if r.status_code != 201:
            raise Exception(f"API Error {r.status_code}: {r.text}")
        return r.json()
