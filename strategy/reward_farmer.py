from models.marketdata import MarketData
from clients.limitless_client import LimitlessClient
from datastreams.deribit_datastream import DeribitDatastream
from datastreams.limitless_datastream import LimitlessDatastream
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class RewardFarmer:
    def __init__(
        self,
        client: LimitlessClient,
        limitless_datastream: LimitlessDatastream,
        deribit_datastream: DeribitDatastream,
        order_amount_usd: float,
        market_data: MarketData
    ):
        self._logger = logger

        self._client = client
        self._market_data = market_data
        self._slug = market_data.slug
        self._yes_token = market_data.yes_token
        self._no_token = market_data.no_token
        self._max_half_spread = Decimal(client.get_max_half_spread())
        self._tick_size = Decimal(client.get_tick_size())
        self._order_amount_usd = Decimal(order_amount_usd)

        self._bba_limit_ratio = Decimal('1.5')
        self._order_limit_ratio = Decimal('3')

        self._limitless_datastream = limitless_datastream
        self._deribit_datastream = deribit_datastream

        self.orders = []

    def _deribit_rewards_band(
        self,
        deribit_target_price: Decimal,
        max_half_spread = Decimal('0.03')
    ) -> tuple[Decimal, Decimal]:
        lo = max(0.0, deribit_target_price - max_half_spread)
        hi = min(1.0, deribit_target_price + max_half_spread)
        return Decimal(lo), Decimal(hi)

    def _limitless_rewards_band(self, midprice: Decimal):
        lo = max(0.0, midprice - self._max_half_spread)
        hi = min(1.0, midprice + self._max_half_spread)
        return Decimal(lo), Decimal(hi)

    def _get_target_deribit_prices(self, deribit_target_price: Decimal) -> tuple[Decimal, Decimal]:
        band = self._deribit_rewards_band(deribit_target_price)
        lower_band, upper_band = (Decimal(x) for x in band)

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
        max_bid: Decimal,
        current_bid: Decimal,
        true_lower_bound: Decimal,
        spread: Decimal,
    ):
        # If current bid is below target_bid, set order at target_bid
        if current_bid < target_bid:
            bid = target_bid
        # Elif current bid is above max_bid, set order at max_bid
        elif current_bid + self._tick_size > max_bid:
            bid = max_bid
        # Otherwise set order 1 tick above current bid
        else:
            bid = current_bid + self._tick_size

        # if the spread is too small, make sure bid is at least the minimum
        if spread < self._max_half_spread * 2:
            bid = max(bid, true_lower_bound)

        return bid

    # Just goes to deribit limits for now, change later so that if the spread is
    # greater than max spread and there is an inventory imbalanace that it will
    # adjust the midprice and quote around it
    def _adjust_bids_for_inventory_difference(
        self,
        target_price: Decimal,
        yes_bid: Decimal,
        no_bid: Decimal,
        deribit_lower_band: Decimal,
        deribit_upper_band: Decimal,
        spread: Decimal,
    ) -> tuple[Decimal, Decimal]:
        shares = self._client.get_shares(self._market_data)
        yes_shares, no_shares = (Decimal(x) for x in shares)

        yes_position = yes_shares * yes_bid
        no_position = no_shares * no_bid
        inventory_difference = yes_position - no_position

        # If there is only inventory difference we just set heavy side to end of reward band
        if inventory_difference > self._order_amount_usd * self._bba_limit_ratio:
            print("too much yes inventory, decreasing bid to end of rewards band")
            yes_bid = deribit_lower_band

        elif inventory_difference < -self._order_amount_usd * self._bba_limit_ratio:
            print("too much no inventory, decreasing bid to end of rewards band")
            no_bid = Decimal('1') - deribit_upper_band

        over_yes_share_threshold = inventory_difference >= self._order_amount_usd * self._order_limit_ratio
        over_no_share_threshold = inventory_difference <= -self._order_amount_usd * self._order_limit_ratio
        max_spread = self._max_half_spread * 2


        # If over max share threshold shift heavy side to sell at target price and light side max spread away
        if over_yes_share_threshold:
            print("over yes inventory threshold, setting no bid to target and yes bid max_spread under")
            no_bid = 1 - target_price
            if spread <= max_spread:
                print(f'spread is less than {max_spread}')
                yes_bid = target_price - self._max_half_spread
            else:
                print(f'spread is greater than {max_spread}')
                yes_bid = target_price - max_spread

        if over_no_share_threshold:
            print("over no inventory threshold, setting yes bid to target and no bid max_spread under")
            yes_bid = target_price
            if spread <= max_spread:
                print(f'spread is less than {max_spread}')
                no_bid = (1 - target_price) - self._max_half_spread
            else:
                print(f'spread is greater than {max_spread}')
                no_bid = (1 - target_price) - max_spread

        return yes_bid, no_bid

    def _keep_prices_in_bounds(self, yes_bid: Decimal, no_bid: Decimal):
        if yes_bid < 0:
            yes_bid = self._tick_size
        if no_bid < 0:
            no_bid = self._tick_size
        return yes_bid, no_bid

    def _find_order_prices(self) -> tuple[Decimal, Decimal]:
        cur_bba = self._limitless_datastream.get_bba()
        cur_yes_bid = Decimal(cur_bba.yes_best_bid)
        cur_yes_ask = Decimal(cur_bba.yes_best_ask)
        cur_no_bid = Decimal(cur_bba.no_best_bid)
        cur_no_ask = Decimal(cur_bba.no_best_ask)

        midprice = (cur_yes_bid + cur_no_ask) / 2
        spread = cur_yes_ask - cur_yes_bid

        if (target := self._deribit_datastream.get_target_price()) is None:
            raise ValueError("Deribit target price is not available")
        deribit_target_price = Decimal(target)
        deribit_lower_band, deribit_upper_band = self._deribit_rewards_band(deribit_target_price)
        true_lower_band, true_upper_band = self._limitless_rewards_band(midprice)
        target_yes_bid, target_no_bid = self._get_target_deribit_prices(deribit_target_price)
        max_yes_bid, max_no_bid = self._get_max_prices(
            target_yes_bid, target_no_bid
        )

        yes_bid = self._calculate_competitive_bid(
            target_bid=target_yes_bid,
            max_bid=max_yes_bid,
            current_bid=cur_yes_bid,
            true_lower_bound=true_lower_band,
            spread=spread
        )
        no_bid = self._calculate_competitive_bid(
            target_bid=target_no_bid,
            max_bid=max_no_bid,
            current_bid=cur_no_bid,
            true_lower_bound=Decimal('1') - true_upper_band,
            spread=spread
        )

        yes_bid, no_bid = self._adjust_bids_for_inventory_difference(
            target_price=target_yes_bid,
            yes_bid=yes_bid,
            no_bid=no_bid,
            deribit_lower_band=deribit_lower_band,
            deribit_upper_band=deribit_upper_band,
            spread=spread
        )

        yes_bid, no_bid = self._keep_prices_in_bounds(yes_bid, no_bid)

        return yes_bid, no_bid

    def _place_replace_orders(self):
        pass
