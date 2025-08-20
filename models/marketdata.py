from dataclasses import dataclass

@dataclass(frozen=True)
class MarketData:
    yes_token: str
    no_token: str
    slug: str
