from typing import Literal

from clients.limitless_client import LimitlessClient
from models.marketdata import MarketData
from models.bba import BBA

class LimitlessDatastream:
    Market = Literal["YES", "NO"] # hardcoded from proxy, probably better way to handle this

    def __init__(self, client: LimitlessClient, market_data: MarketData):
        self.market_data = client.get_market_data(market_data.slug)

        self._client = client
        self.slug = market_data.slug
        self.yes_token_id = self.market_data.yes_token
        self.no_token_id = self.market_data.no_token

        self.yes_best_bid = None
        self.yes_best_ask = None
        self.no_best_bid = None
        self.no_best_ask = None

    def update_bba(self):
        bba = self._client.get_bba(self.market_data)
        self.yes_best_bid = bba.yes_best_bid
        self.yes_best_ask = bba.yes_best_ask
        self.no_best_bid = bba.no_best_bid
        self.no_best_ask = bba.no_best_ask

    def get_bba(self):
        self.update_bba()
        return BBA(self.yes_best_bid, self.yes_best_ask, self.no_best_bid, self.no_best_ask)
