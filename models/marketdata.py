from dataclasses import dataclass

@dataclass(frozen=True)
class MarketData:
    slug: str
    yes_token: str
    no_token: str
