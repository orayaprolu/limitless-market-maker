"""
Constants for the Limitless Market Maker application.
Contains all configuration constants, URLs, addresses, and other constant values.
"""

# Limitless Exchange Configuration
LIMITLESS_URL = "https://api.limitless.exchange"
LIMITLESS_CLOB_CFT_ADDRS = "0xa4409D988CA2218d956BeEFD3874100F444f0DC3"
LIMITLESS_NEGRISK_CFT_ADDRS = "0x5a38afc17F7E97ad8d6C547ddb837E40B4aEDfC6"
LIMITLESS_ERC1155_CFT_ADDRS = "0xC9c98965297Bc527861c898329Ee280632B76e18"
LIMITLESS_OPERATOR_CTF_ADDRS = "0xa4409D988CA2218d956BeEFD3874100F444f0DC3"

# Base Network Configuration
BASE_RPC = "https://mainnet.base.org"
BASE_CHAIN_ID = 8453

# Trading Constants
DEFAULT_GAS_LIMIT = 300000
DEFAULT_GAS_PRICE_GWEI = 1
MAX_SLIPPAGE = 0.05  # 5%

# API Rate Limits
LIMITLESS_RATE_LIMIT = 10  # requests per second
DERIBIT_RATE_LIMIT = 5    # requests per second

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

# Logging Configuration
DEFAULT_LOG_LEVEL = "WARNING"
STRATEGY_LOG_LEVEL = "DEBUG"
INFO_LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Market Data Constants
BID_ASK_SPREAD_THRESHOLD = 0.01  # 1%
MIN_LIQUIDITY = 100  # minimum liquidity required
