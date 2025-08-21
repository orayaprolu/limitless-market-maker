from typing import TypedDict, NotRequired, Literal, List, Union

# --- GET /markets/{slug}/orderbook ---
class OBLevel(TypedDict):
    price: float
    size: int

class OrderbookDTO(TypedDict, total=False):
    adjustedMidpoint: float
    asks: List[OBLevel]
    bids: List[OBLevel]
    lastTradePrice: float
    maxSpread: float
    minSize: int
    tokenId: str

# --- POST /orders (request body) ---
class OrderDTO(TypedDict, total=False):
    salt: int
    maker: str
    signer: str
    taker: str
    tokenId: Union[str, int]
    makerAmount: int
    takerAmount: int
    expiration: Union[str, int]
    nonce: int
    price: float
    feeRateBps: int
    side: Literal[0, 1]
    signature: str
    signatureType: int

class CreateOrderBodyDTO(TypedDict):
    order: OrderDTO
    ownerId: str
    orderType: Literal["GTC", "IOC", "FOK"]
    marketSlug: str

# --- POST /orders (response) ---
class MatchDTO(TypedDict, total=False):
    # API example shows [] — keep flexible
    # Fill in if you later rely on specific fields
    pass

class CreateOrderResponseDTO(TypedDict, total=False):
    order: OrderDTO
    makerMatches: List[MatchDTO]
    takerMatches: NotRequired[List[MatchDTO]]
