from models.marketdata import MarketData
from clients.limitless_client import LimitlessClient
from datastreams.deribit_datastream import DeribitDatastream
from datastreams.limitless_datastream import LimitlessDatastream
from decimal import Decimal


class RewardFarmer:
    def __init__(
        self,
        client: LimitlessClient,
        limitless_datastream: LimitlessDatastream,
        deribit_datastream: DeribitDatastream,
        market_data: MarketData
    ):
        self._client = client
        self._slug = market_data.slug
        self._yes_token = market_data.yes_token
        self._no_token = market_data.no_token
        self._max_half_spread = Decimal(client.get_max_half_spread())
        self._tick_size = Decimal(client.get_tick_size())

        self._limitless_datastream = limitless_datastream
        self._deribit_datastream = deribit_datastream

        self.orders = []

    def _deribit_rewards_band(
        self, max_half_spread: float = 0.03
    ) -> tuple[float, float] | None:
        deribit_target_price = self._deribit_datastream.get_target_price()
        if not deribit_target_price:
            return None
        lo = max(0.0, deribit_target_price - max_half_spread)
        hi = min(1.0, deribit_target_price + max_half_spread)
        return lo, hi

    def _get_target_deribit_prices(self) -> tuple[Decimal, Decimal]:
        band = self._deribit_rewards_band()
        if not band:
           raise ValueError("Deribit rewards band not found")
        lower_band, upper_band = (Decimal(x) for x in band)

        target_price = self._deribit_datastream.get_target_price()
        if not target_price:
            raise ValueError("Deribit target price not found")

        target_price = Decimal(target_price)
        target_yes_bid = lower_band
        target_no_bid = Decimal('1') - upper_band

        return target_yes_bid, target_no_bid

    def _get_max_prices(
        self,
        target_yes_bid: Decimal,
        target_no_bid: Decimal
    ) -> tuple[Decimal, Decimal]:
        max_yes_bid = target_yes_bid + (self._max_half_spread / 2)
        max_no_bid = target_no_bid + (self._max_half_spread / 2)

        return max_yes_bid, max_no_bid

    def _calculate_competitive_bid(
        self,
        target_bid: Decimal,
        min_bid: Decimal,
        max_bid: Decimal,
        current_bid: Decimal,
        spread: Decimal,
    ):
        if current_bid > target_bid:
            bid = target_bid
        elif current_bid + self.
        pass

    def _find_order_prices(self):
        target_yes_bid, target_no_bid = self._get_target_deribit_prices()
        max_yes_bid, max_no_bid = self._get_max_prices(
            target_yes_bid, target_no_bid
        )

        cur_bba = self._limitless_datastream.get_bba()
        cur_yes_bid = Decimal(cur_bba.yes_best_bid)
        cur_yes_ask = Decimal(cur_bba.yes_best_ask)
        cur_no_bid = Decimal(cur_bba.no_best_bid)
        cur_no_ask = Decimal(cur_bba.no_best_ask)






    def _place_replace_orders(self):
        pass
