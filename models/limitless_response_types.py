from typing import TypedDict, NotRequired, Literal, List, Union, Dict, Any

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
    id: str
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

# --- rewardsChartData item ---
class RewardsChartDataDTO(TypedDict, total=False):
    timestamp: int
    userRewards: str
    totalRewards: str


# --- rewardsByEpoch item ---
class RewardsByEpochDTO(TypedDict, total=False):
    epochId: int
    timestamp: str
    totalRewards: str
    userRewards: str
    earnedPercent: float


# --- rewards section ---
class RewardsDTO(TypedDict, total=False):
    todaysRewards: str
    totalUnpaidRewards: str
    totalUserRewardsLastEpoch: str
    rewardsChartData: List[RewardsChartDataDTO]
    rewardsByEpoch: List[RewardsByEpochDTO]


# --- amm section ---
class AmmDTO(TypedDict, total=False):
    collateralAmount: str
    latestTrade: Dict[str, Any]
    market: Dict[str, Any]
    outcomeIndex: int
    outcomeTokenAmount: str


# --- clob positions (yes/no) ---
class ClobPositionDTO(TypedDict, total=False):
    cost: str
    fillPrice: str
    realisedPnl: str
    unrealizedPnl: str
    marketValue: str


class ClobPositionsDTO(TypedDict, total=False):
    yes: ClobPositionDTO
    no: ClobPositionDTO


# --- clob item ---
class ClobDTO(TypedDict, total=False):
    market: Dict[str, Any]          # you can refine if needed
    positions: ClobPositionsDTO
    latestTrade: Dict[str, Any]
    tokensBalance: Dict[str, Any]
    orders: Dict[str, Any]
    rewards: Dict[str, Any]


# --- top-level portfolio history response ---
class PortfolioHistoryDTO(TypedDict, total=False):
    rewards: RewardsDTO
    amm: List[AmmDTO]
    clob: List[ClobDTO]

# --- tokens DTO section ---
class TokensDTO(TypedDict):
    yes: str
    no: str
