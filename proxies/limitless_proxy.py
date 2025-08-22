from dotenv import load_dotenv
from typing import Literal, Optional, NamedTuple, Tuple, get_args
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct, encode_typed_data
import requests
import time
import logging
import json
from decimal import Decimal
import math
import random

from utils.rate_limit import SpacedLimiter
from utils.string_to_hex import string_to_hex
from config import (
    LIMITLESS_URL, BASE_RPC, LIMITLESS_CLOB_CFT_ADDRS,
    LIMITLESS_NEGRISK_CFT_ADDRS, LIMITLESS_ERC1155_CFT_ADDRS,
    LIMITLESS_OPERATOR_CTF_ADDRS, BASE_CHAIN_ID
)
from models.marketdata import MarketData
from models.limitless_response_types import (
    OrderbookDTO, CreateOrderBodyDTO,
    CreateOrderResponseDTO, OrderDTO,
    PortfolioHistoryDTO, TokensDTO
)


load_dotenv()

logger = logging.getLogger(__name__)

class LimitlessProxy:
    _EIP712_ORDER_TYPES = {
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

    _ERC1155_ABI = [
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


    class LoginSession(NamedTuple):
        ts: float
        cookie: str
        user_data: dict

    class SignedMessage(NamedTuple):
        ts: float
        message: str

    def __init__(self, private_key):
        self._logger = logger.getChild(__class__.__name__)
        self._limiter = SpacedLimiter(min_interval_s=5)

        if not private_key:
            raise ValueError("Private key is required")

        self._account = Account.from_key(private_key)
        self._private_key: str = private_key
        self._public_key: str = self._account.address
        self._api_url: str = LIMITLESS_URL

        # Use checksume since Web3 package checks validity of address by verifying if valid checksum
        self._clob_address = Web3.to_checksum_address(LIMITLESS_CLOB_CFT_ADDRS)
        self._negrisk_address = Web3.to_checksum_address(LIMITLESS_NEGRISK_CFT_ADDRS)
        self._ctf_erc1155_addr = Web3.to_checksum_address(LIMITLESS_ERC1155_CFT_ADDRS)
        self._operator_ctf_addr = Web3.to_checksum_address(LIMITLESS_OPERATOR_CTF_ADDRS)

        self._rpc: str = BASE_RPC
        self._chain_id: int = BASE_CHAIN_ID
        self._w3 = Web3(Web3.HTTPProvider(BASE_RPC))
        self._ensure_ctf_sell_approval(self._private_key)

        self._signed_message_cache: Optional[LimitlessProxy.SignedMessage] = None
        self._login_cache: Optional[LimitlessProxy.LoginSession] = None

    def __repr__(self):
        return f"LimitlessProxy(public_key={self._public_key!r})"

    def _gated_request(self, method: str, path: str, **kwargs) -> requests.Response:
        base = self._api_url.rstrip("/")
        url = f"{base}{path}"

        for attempt in range(4):
            self._limiter.acquire()
            r = requests.request(method, url, timeout=35, **kwargs)

            # retry only when it's likely transient
            if r.status_code in (429, 500, 502, 503, 504):
                backoff = min(2 ** attempt, 8) + random.random() * 0.4
                time.sleep(backoff)
                continue

            return r

        self._limiter.acquire()
        r = requests.request(method, url, timeout=35, **kwargs)
        return r

    def _gated_get(self, path: str, **kwargs):  return self._gated_request("GET", path, **kwargs)

    def _gated_post(self, path: str, **kwargs): return self._gated_request("POST", path, **kwargs)

    def _gated_delete(self, path: str, **kwargs): return self._gated_request("DELETE", path, **kwargs)

    def _ensure_ctf_sell_approval(self, private_key: str):
        public_key = Web3.to_checksum_address(self._account.address)
        operator = self._operator_ctf_addr
        ctf = self._w3.eth.contract(address=self._ctf_erc1155_addr, abi=self._ERC1155_ABI)


        try:
            already_approved = ctf.functions.isApprovedForAll(public_key, operator).call({"from": public_key})
        except Exception as e:
            self._logger.warning(f"isApprovedForAll({operator}) view failed (continuing):", e)
            already_approved = False

        if already_approved:
            self._logger.info(f"Already approved CTF for transfer to operator: {operator}")

        try:
            gas_est = ctf.functions.setApprovalForAll(operator, True).estimate_gas({"from": public_key})
            print(f"approval gas estimate for {operator}: {gas_est}")
        except Exception as eg:
            raise RuntimeError(f"❌ setApprovalForAll would revert for operator {operator}: {eg}")

        tx = ctf.functions.setApprovalForAll(operator, True).build_transaction({
            "from": public_key,
            "nonce": self._w3.eth.get_transaction_count(public_key),
            "maxFeePerGas": self._w3.to_wei("0.5", "gwei"),
            "maxPriorityFeePerGas": self._w3.to_wei("0.1", "gwei"),
            "gas": int(gas_est * 1.2),
            "chainId": 8453,
        })
        signed = self._w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        self._logger.debug(f"Sent transaction for approval of CTF for transfer to operator: {operator}")
        rcpt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
        if rcpt.status != 1: # pyright: ignore
            raise RuntimeError(f"❌ setApprovalForAll failed on-chain for operator {operator}")
        self._logger.info(f"ERC1155 approval confirmed for operator {operator}")

    def _get_signing_message(self):
        now = time.time()
        max_cache_age = 60
        if self._signed_message_cache and self._signed_message_cache.ts + max_cache_age > now:
            self._logger.debug(f"Using cached signing message {self._signed_message_cache}")
            return self._signed_message_cache.message

        r = self._gated_get('/auth/signing-message')
        if r.status_code != 200:
            raise Exception(f"Failed to get signing message: {r.text}")
        self._signed_message_cache = self.SignedMessage(ts=now, message=r.text)
        self._login_cache = None # force new login
        self._logger.debug(f'Set signed_message_cache {self._signed_message_cache}')
        return r.text

    def _login(self, signing_message: str):
        now = time.time()
        max_cache_age = 60

        if self._login_cache and self._login_cache.ts + max_cache_age > now:
            self._logger.debug("Using cached login session")
            return self._login_cache.cookie, self._login_cache.user_data

        self._logger.debug(f'Using account {self._account.address}')

        signing_message_hash = encode_defunct(text=signing_message)
        signature = self._account.sign_message(signing_message_hash).signature.hex()
        if not signature.startswith("0x"):
            signature = "0x" + signature
        signing_message = string_to_hex(signing_message)

        headers = {
            'x-account': self._account.address,
            'x-signature': signature,
            'x-signing-message': signing_message,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        body = {"client": "eoa"}
        r = self._gated_post('/auth/login', headers=headers, json=body)
        if r.status_code != 200:
            raise Exception(f"Authentication failed: {r.status_code} - {r.text}")
        self._logger.debug(f'Logged in successfully: {r.text}')

        cookie = r.cookies.get("limitless_session")
        if not cookie:
            raise Exception("Failed to retrieve session cookie")
        user_data = r.json()
        self._login_cache = self.LoginSession(ts=now, cookie=cookie, user_data=user_data)

        return cookie, user_data

    def _get_eip712_order_domain(self):
        return {
            'name': 'Limitless CTF Exchange',
            'version': '1',
            'chainId': self._chain_id,
            'verifyingContract': self._clob_address
        }

    def _create_order_payload_without_signature(
        self,
        maker_address,
        token_id,
        maker_amount,
        taker_amount,
        fee_rate_bps,
        side
    ) -> OrderDTO :
        salt = int(time.time() * 1000) + (24 * 60 * 60 * 1000)
        if side == 'BUY':
            side_flag = 0
        elif side == 'SELL':
            side_flag = 1
        else:
            raise ValueError("Invalid side")
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


        domain = self._get_eip712_order_domain()

        try:
            encoded = encode_typed_data(
                domain_data=domain,
                message_types=self._EIP712_ORDER_TYPES,
                message_data=msg,
            )
        except Exception:
            encoded = encode_typed_data({
                "types": self._EIP712_ORDER_TYPES,
                "primaryType": "Order",
                "domain": domain,
                "message": msg,
            })

        acct = Account.from_key(self._private_key if self._private_key.startswith("0x") else "0x" + self._private_key)
        signed = acct.sign_message(encoded)
        sig = signed.signature.hex()
        if not sig.startswith("0x"):
            sig = "0x" + sig
        return sig

    def _create_order_api(self, order_payload, session_cookie):
        headers = {
            "cookie": f"limitless_session={session_cookie}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._logger.info(f"Order payload: {json.dumps(order_payload, indent=2)}")
        r = self._gated_post('/orders', headers=headers, json=order_payload)
        if r.status_code != 201:
            self._logger.error(f"Failed to create order. Status: {r.status_code}")
            self._logger.error(f"Response: {r.text}")
            raise Exception(f"API Error {r.status_code}: {r.text}")
        out: CreateOrderResponseDTO = r.json()
        self._logger.info(f"Order created successfully: {json.dumps(out, indent=2)}")
        return out

    def place_order(
        self,
        price_dollars: float,
        shares: int,
        market_type: LimitlessProxy.Market,
        side: LimitlessProxy.Side,
        market_data: MarketData,
    ) -> CreateOrderResponseDTO:
        if market_type not in get_args(self.Market):
            raise ValueError("market_type must be 'YES' or 'NO'")

        signing_message = self._get_signing_message()
        session_cookie, user_data = self._login(signing_message)
        self._logger.info("Logged in successfully")

        scaling_factor = 10 ** 6
        token_id = market_data.yes_token if market_type == "YES" else market_data.no_token

        price = Decimal(str(price_dollars))
        fee_bps = int(user_data.get("rank", {}).get("feeRateBps", 0))
        fee = Decimal(fee_bps) / Decimal(10_000.0)
        shares = int(shares)

        if side == "BUY":
            contracts_amount = shares * scaling_factor
            collateral_amount = math.floor(price * Decimal(contracts_amount))

            maker_amount = int(collateral_amount)
            taker_amount = int(contracts_amount)

        elif side == "SELL":
            contracts_pre = shares * scaling_factor
            contracts_after = math.floor(Decimal(contracts_pre) * (Decimal(1.0) - fee))
            collateral_amount = math.floor(price * Decimal(contracts_after))

            maker_amount = int(contracts_after)
            taker_amount = int(collateral_amount)

        else:
            raise ValueError("side must be 'BUY' or 'SELL'")

        unsigned_order = self._create_order_payload_without_signature(
            maker_address=self._account.address,
            token_id=token_id,
            maker_amount=maker_amount,
            taker_amount=taker_amount,
            fee_rate_bps=fee_bps,
            side=side
        )
        signature = self._create_signature_for_order_payload(unsigned_order)

        final_order_payload: CreateOrderBodyDTO = {
            "order": { **unsigned_order, "price": float(price_dollars), "signature": signature },
            "ownerId": user_data["id"],
            "orderType": "GTC",
            "marketSlug": market_data.slug,
        }

        return self._create_order_api(final_order_payload, session_cookie)

    def cancel_order(self, order_id: str) -> bool:
        signing_message = self._get_signing_message()
        session_cookie, user_data = self._login(signing_message)
        headers = {
            "cookie": f"limitless_session={session_cookie}",
        }

        self._logger.info(f"Canceling order with ID {order_id}")
        r = self._gated_delete(f'/orders/{order_id}', headers=headers)
        if r.status_code == 200:
            self._logger.info("Order canceled successfully")
            return True
        elif r.status_code == 400:
            self._logger.warning(f"Order {order_id} cannot be canceled: {r.text}")
            return False
        elif r.status_code == 401:
            raise Exception("Not authorized to cancel this order")
        else:
            r.raise_for_status()

        return False

    def get_portfolio_history(self) -> PortfolioHistoryDTO:
        signing_message = self._get_signing_message()
        session_cookie, user_data = self._login(signing_message)
        headers = {
            "cookie": f"limitless_session={session_cookie}",
        }

        r = self._gated_get("/portfolio/history", headers=headers)
        r.raise_for_status()
        return r.json()

    def get_orderbook(self, market_data: MarketData) -> OrderbookDTO:
        r = self._gated_get(f'/markets/{market_data.slug}/orderbook')
        r.raise_for_status()
        data: OrderbookDTO = r.json()
        return data

    def get_token_ids(self, slug: str) -> TokensDTO:
        r = self._gated_get(f'/markets/{slug}')
        r.raise_for_status()
        tokens: TokensDTO = r.json()['tokens']
        return tokens
