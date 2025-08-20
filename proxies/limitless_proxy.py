from dotenv import load_dotenv
from typing import Literal, Optional, NamedTuple
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import requests
import time
import logging
import os

from utils.string_to_hex import string_to_hex
from config import (
    LIMITLESS_URL, BASE_RPC, LIMITLESS_CLOB_CFT_ADDRS,
    LIMITLESS_NEGRISK_CFT_ADDRS, LIMITLESS_ERC1155_CFT_ADDRS,
    LIMITLESS_OPERATOR_CTF_ADDRS, BASE_CHAIN_ID
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

    _ERC165_ABI = [
        {"constant": True, "inputs": [{"name":"interfaceId","type":"bytes4"}],
         "name":"supportsInterface", "outputs":[{"name":"","type":"bool"}],
         "stateMutability":"view","type":"function"}
    ]

    Market = Literal["YES", "NO"]
    Side = Literal["BUY", "SELL"]
    class SignedMessage(NamedTuple):
        ts: float
        message: str

    def __init__(self, public_key, private_key):
        self.logger = logger.getChild(__class__.__name__)

        if not public_key:
            raise ValueError("Public key is required")
        if not private_key:
            raise ValueError("Private key is required")

        self._public_key: str = public_key
        self._private_key: str = private_key
        self._api_url: str = LIMITLESS_URL

        # Use checksume since Web3 package checks validity of address by verifying if valid checksum
        self._clob_address: str = Web3.to_checksum_address(LIMITLESS_CLOB_CFT_ADDRS)
        self._negrisk_address: str = Web3.to_checksum_address(LIMITLESS_NEGRISK_CFT_ADDRS)
        self._ctf_erc1155_addr: str = Web3.to_checksum_address(LIMITLESS_ERC1155_CFT_ADDRS)
        self._operator_ctf_addr: str = Web3.to_checksum_address(LIMITLESS_OPERATOR_CTF_ADDRS)

        self._rpc: str = BASE_RPC
        self._chain_id: int = BASE_CHAIN_ID

        self._signed_message_cache: Optional[LimitlessProxy.SignedMessage] = None

    def __repr__(self):
        return f"LimitlessProxy(public_key={self._public_key!r})"

    def _get_signing_message(self):
        now = time.time()
        max_cache_age = 60
        if self._signed_message_cache and self._signed_message_cache.ts + max_cache_age > now:
            self.logger.debug(f"Using cached signing message {self._signed_message_cache}")
            return self._signed_message_cache.message

        r = requests.get(f'{self._api_url}/auth/signing-message')
        if r.status_code != 200:
            raise Exception(f"Failed to get signing message: {r.text}")
        self._signed_message_cache = self.SignedMessage(ts=now, message=r.text)
        self.logger.debug(f'Set signed_message_cache {self._signed_message_cache}')
        return r.text

    def _login(self, private_key: str, signing_message: str):
        account = Account.from_key(private_key)
        self.logger.debug(f'Using account {account.address}')

        signing_message_hash = encode_defunct(text=signing_message)
        signing_message = string_to_hex(signing_message)
        signature = account.sign_message(signing_message_hash).signature.hex()

        headers = {
            'x-account': account.address,
            'x-signature': signature,
            'x-signature-message': signing_message,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        body = {"client": "eoa"}
        r = requests.post(f'{self._api_url}/auth/login', headers=headers, json=body)
        if r.status_code != 200:
            raise Exception(f"Authentication failed: {r.status_code} - {r.text}")
        self.logger.debug(f'Logged in successfully: {r.text}')
        return r.cookies.get("limitless_session"), r.json()

    def _get_eip712_order_domain(self):
        return {
            'name': 'Limitless',
            'version': '1',
            'chainId': self._chain_id,
            'verifyingContract': self._clob_address
        }

    def _create_order_payload_without_signature(self, maker_address, token_id, maker_amount, taker_amount, fee_rate_bps, side_flag):
        salt = os.urandom(32)
