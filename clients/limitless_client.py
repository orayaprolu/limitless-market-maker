from typing import Literal
import math
from decimal import Decimal

from proxies.limitless_proxy import LimitlessProxy
from models.marketdata import MarketData
from models.bba import BBA


class LimitlessClient:
    # Just ripped these from the proxy for now, should prob move this to models
    Market = Literal["YES", "NO"]
    Side = Literal["BUY", "SELL"]

    def __init__(self, private_key: str):
        self._proxy = LimitlessProxy(private_key)

    def get_market_data(self, slug: str):
        if not slug:
            raise ValueError("Slug is required")

        tokens = self._proxy.get_token_ids(slug)
        yes_token_id, no_token_id = tokens['yes'], tokens['no']

        market_data = MarketData(slug=slug, yes_token=yes_token_id, no_token=no_token_id)
        return market_data

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

    def get_bba(self, market_data: MarketData):
        orderbook = self._proxy.get_orderbook(market_data)

        if 'bids' in orderbook and 'asks' in orderbook:
            yes_best_bid = orderbook['bids'][0]['price']
            yes_best_ask = orderbook['asks'][0]['price']

            no_best_bid = Decimal("1") - Decimal(str(orderbook['asks'][0]['price']))
            no_best_ask = Decimal("1") - Decimal(str(orderbook['bids'][0]['price']))

            return BBA(yes_best_bid, yes_best_ask, float(no_best_bid), float(no_best_ask))

        else:
            raise ValueError("No orderbook data returned in response")

    def get_shares(self, market_data: MarketData):
        port_json = self._proxy.get_portfolio_history()

        try:
            positions = port_json.get('clob', [])
        except Exception as e:
            raise ValueError("No position data returned in response") from e

        market = next(
            (x for x in positions if x['market']['slug'] == market_data.slug),
            None
        )
        if market is None:
            return 0, 0

        decimal_amount = 10 ** 6

        yes_shares = float(market['tokensBalance']['yes']) / decimal_amount
        no_shares = float(market['tokensBalance']['no']) / decimal_amount

        return yes_shares, no_shares

    def cancel_order(self, order_id: str):
        return self._proxy.cancel_order(order_id)

    def cancel_orders(self, order_ids: list[str]):
        for order_id in order_ids:
            self._proxy.cancel_order(order_id)

    # THIS ONLY RETURNS 0.03 RIGHT NOW !
    def get_max_half_spread(self):
        return 0.03

    # THIS ONLY RETURNS 0.001 RIGHT NOW !
    def get_tick_size(self):
        return 0.001
