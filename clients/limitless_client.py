from typing import Literal
import math
from collections import namedtuple

from proxies.limitless_proxy import LimitlessProxy
from models.marketdata import MarketData

class LimitlessClient:
    # Just ripped these from the proxy for now, should prob move this to models
    Market = Literal["YES", "NO"]
    Side = Literal["BUY", "SELL"]

    BBA = namedtuple('BBA', ['best_yes_bid', 'best_yes_ask', 'best_no_bid', 'best_no_ask'])

    def __init__(self, private_key: str):
        self._proxy = LimitlessProxy(private_key)

    def get_token_ids(self, slug: str):
        if not slug:
            raise ValueError("Slug is required")

        tokens = self._proxy.get_token_ids(slug)
        yes_token_id, no_token_id = tokens['yes'], tokens['no']

        return yes_token_id, no_token_id

    def buy_yes(self, price_dollars: float, usd_amount: float, market_data: MarketData):
        shares = math.floor(usd_amount / price_dollars)
        order = self._proxy.place_order(
            price_dollars=price_dollars,
            shares=shares,
            market_type='YES',
            side='BUY',
            market_data=market_data
        )

        if "order" in order and "id" in order["order"]:
            return order["order"]["id"]
        else:
            raise ValueError("No order returned in response")

    def buy_no(self, price_dollars: float, usd_amount: float, market_data: MarketData):
        shares = math.floor(usd_amount / price_dollars)
        order = self._proxy.place_order(
            price_dollars=price_dollars,
            shares=shares,
            market_type='NO',
            side='BUY',
            market_data=market_data
        )

        if "order" in order and "id" in order["order"]:
            return order["order"]["id"]
        else:
            raise ValueError("No order returned in response")

    def sell_yes(self, price_dollars: float, shares: int, market_data: MarketData):
        order = self._proxy.place_order(
            price_dollars=price_dollars,
            shares=shares,
            market_type='YES',
            side='SELL',
            market_data=market_data
        )

        if "order" in order and "id" in order["order"]:
            return order["order"]["id"]
        else:
            raise ValueError("No order returned in response")

    def sell_no(self, price_dollars: float, shares: int, market_data: MarketData):
        order = self._proxy.place_order(
            price_dollars=price_dollars,
            shares=shares,
            market_type='NO',
            side='SELL',
            market_data=market_data
        )

        if "order" in order and "id" in order["order"]:
            return order["order"]["id"]
        else:
            raise ValueError("No order returned in response")

    def get_bbas(self, market_data: MarketData):
        orderbook = self._proxy.get_orderbook(market_data)

        if 'bids' in orderbook and 'asks' in orderbook:
            yes_best_bid = orderbook['bids'][-1]['price']
            yes_best_ask = orderbook['asks'][-1]['price']

            no_best_bid = 1 - orderbook['asks'][-1]['price']
            no_best_ask = orderbook['bids'][-1]['price']

            return self.BBA(yes_best_bid, yes_best_ask, no_best_bid, no_best_ask)

        else:
            raise ValueError("No orderbook data returned in response")
