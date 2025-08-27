from decimal import Decimal
import logging
import math
import time
from typing import Literal

from models.marketdata import MarketData
from clients.limitless_client import LimitlessClient
from datastreams.deribit_datastream import DeribitDatastream
from datastreams.limitless_datastream import LimitlessDatastream
from utils.snap import safe_snap_up, safe_snap_down

logger = logging.getLogger(__name__)

class RewardFarmer:
    Market = Literal["YES", "NO"]

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

        self._prev_yes_bid = Decimal('-1')
        self._prev_no_bid = Decimal('-1')

        self._orders = []

        self._logger.info(f"Initialized RewardFarmer for market {self._slug}")
        self._logger.info(f"Order amount: ${order_amount_usd}, Max half spread: {self._max_half_spread}, Tick size: {self._tick_size}")

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
        market: Market
    ):
        if market == 'YES':
            prev_bid = self._prev_yes_bid
        elif market == 'NO':
            prev_bid = self._prev_no_bid
        else:
            raise ValueError(f"Invalid market: {market}")


        # If current bid is below target_bid, set order at target_bid
        if current_bid < target_bid:
            bid = target_bid
            self._logger.debug(f"Current bid {current_bid} below target {target_bid}, setting to target")
        # Elif current bid is above max_bid, set order at max_bid
        elif current_bid + self._tick_size > max_bid:
            bid = max_bid
            self._logger.debug(f"Current bid {current_bid} above max {max_bid}, setting to max")
        # If we have active orders, never outbid ourselves
        elif self._orders:
            bid = current_bid
            self._logger.debug(f"Active orders exist, maintaining current bid {current_bid}")
        # Only increase bid if the market has moved up and we don't have orders
        elif prev_bid != current_bid and current_bid > prev_bid:
            bid = current_bid + self._tick_size
            self._logger.debug(f"Market bid increased from {prev_bid} to {current_bid}, setting to {bid}")
        else:
            bid = current_bid
            self._logger.debug(f"Maintaining current bid {current_bid}")

        # if the spread is too small, make sure bid is at least the minimum
        if spread < self._max_half_spread * 2:
            bid = max(bid, true_lower_bound)
            self._logger.debug(f"Spread {spread} too small, ensuring bid >= {true_lower_bound}")

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

        self._logger.info(f"Inventory difference: ${inventory_difference:.2f} (yes: {yes_shares:.2f}, no: {no_shares:.2f})")

        # If there is only inventory difference we just set heavy side to end of reward band
        if inventory_difference > self._order_amount_usd * self._bba_limit_ratio:
            self._logger.info("Too much yes inventory, decreasing bid to end of rewards band")
            yes_bid = deribit_lower_band

        elif inventory_difference < -self._order_amount_usd * self._bba_limit_ratio:
            self._logger.info("Too much no inventory, decreasing bid to end of rewards band")
            no_bid = Decimal('1') - deribit_upper_band

        over_yes_share_threshold = inventory_difference >= self._order_amount_usd * self._order_limit_ratio
        over_no_share_threshold = inventory_difference <= -self._order_amount_usd * self._order_limit_ratio
        max_spread = self._max_half_spread * 2


        # If over max share threshold shift heavy side to sell at target price and light side max spread away
        if over_yes_share_threshold:
            self._logger.warning("Over yes inventory threshold, setting no bid to target and yes bid max_spread under")
            no_bid = 1 - target_price
            if spread <= max_spread:
                self._logger.debug(f'Spread {spread} is less than {max_spread}')
                yes_bid = target_price - self._max_half_spread
            else:
                self._logger.debug(f'Spread {spread} is greater than {max_spread}')
                yes_bid = target_price - max_spread

        if over_no_share_threshold:
            self._logger.warning("Over no inventory threshold, setting yes bid to target and no bid max_spread under")
            yes_bid = target_price
            if spread <= max_spread:
                self._logger.debug(f'Spread {spread} is less than {max_spread}')
                no_bid = (1 - target_price) - self._max_half_spread
            else:
                self._logger.debug(f'Spread {spread} is greater than {max_spread}')
                no_bid = (1 - target_price) - max_spread

        return yes_bid, no_bid

    def _keep_prices_in_bounds(self, yes_bid: Decimal, no_bid: Decimal):
        if yes_bid < 0:
            yes_bid = self._tick_size
        if no_bid < 0:
            no_bid = self._tick_size
        return yes_bid, no_bid

    def _find_order_prices(self) -> tuple[Decimal, Decimal]:
        global cur_bba  # Make cur_bba available to the trading loop
        cur_bba = self._limitless_datastream.get_bba()
        cur_yes_bid = Decimal(cur_bba.yes_best_bid)
        cur_yes_ask = Decimal(cur_bba.yes_best_ask)
        cur_no_bid = Decimal(cur_bba.no_best_bid)
        cur_no_ask = Decimal(cur_bba.no_best_ask)

        midprice = (cur_yes_bid + cur_yes_ask) / 2
        spread = cur_yes_ask - cur_yes_bid

        self._logger.debug(f"Current BBA - Yes: {cur_yes_bid}/{cur_yes_ask}, No: {cur_no_bid}/{cur_no_ask}")
        self._logger.debug(f"Midprice: {midprice:.3f}, Spread: {spread:.3f}")

        if (target := self._deribit_datastream.get_target_price()) is None:
            self._logger.error("Deribit target price is not available")
            raise ValueError("Deribit target price is not available")
        deribit_target_price = Decimal(target)
        self._logger.debug(f"Deribit target price: {deribit_target_price:.3f}")
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
            spread=spread,
            market='YES'
        )
        no_bid = self._calculate_competitive_bid(
            target_bid=target_no_bid,
            max_bid=max_no_bid,
            current_bid=cur_no_bid,
            true_lower_bound=Decimal('1') - true_upper_band,
            spread=spread,
            market='NO'
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

        self._logger.info(f"Final order prices - Yes bid: {yes_bid:.3f}, No bid: {no_bid:.3f}")
        return yes_bid, no_bid

    def _place_orders(self, yes_bid: Decimal, no_bid: Decimal):
        inventory = self._client.get_shares(self._market_data)
        yes_shares_inventory, no_shares_inventory = inventory

        yes_ask = Decimal('1') - no_bid
        no_ask = Decimal('1') - yes_bid
        yes_shares_to_sell = math.floor(self._order_amount_usd / yes_ask)
        no_shares_to_sell = math.floor(self._order_amount_usd / no_ask)

        self._logger.debug(f"Inventory: Yes {yes_shares_inventory:.2f}, No {no_shares_inventory:.2f}")

        sold_yes = False
        if yes_shares_to_sell <= yes_shares_inventory:
            order_yes_ask = float(yes_ask)
            self._logger.info(f"Selling YES: {yes_shares_to_sell} shares @ ${order_yes_ask:.3f}")
            order_id = self._client.sell_yes(
                order_yes_ask, yes_shares_to_sell, self._market_data
            )
            self._orders.append(order_id)
            self._logger.debug(f"YES sell order placed with ID: {order_id}")
            sold_yes = True

        sold_no = False
        if no_shares_to_sell <= no_shares_inventory:
            order_no_ask = float(no_ask)
            self._logger.info(f"Selling NO: {no_shares_to_sell} shares @ ${order_no_ask:.3f}")
            order_id = self._client.sell_no(
                order_no_ask, no_shares_to_sell, self._market_data
            )
            self._orders.append(order_id)
            self._logger.debug(f"NO sell order placed with ID: {order_id}")
            sold_no = True


        yes_shares_to_sell = math.floor(self._order_amount_usd / yes_bid)
        no_shares_to_sell = math.floor(self._order_amount_usd / no_bid)
        order_yes_bid = float(yes_bid)
        order_no_bid = float(no_bid)

        if not sold_yes:
            self._logger.info(f"Buying YES: ${float(self._order_amount_usd):.2f} @ ${order_yes_bid:.3f}")
            order_id = self._client.buy_yes(
                order_yes_bid, float(self._order_amount_usd), self._market_data
            )
            self._orders.append(order_id)
            self._logger.debug(f"YES buy order placed with ID: {order_id}")
        if not sold_no:
            self._logger.info(f"Buying NO: ${float(self._order_amount_usd):.2f} @ ${order_no_bid:.3f}")
            order_id = self._client.buy_no(
                order_no_bid, float(self._order_amount_usd), self._market_data
            )
            self._orders.append(order_id)
            self._logger.debug(f"NO buy order placed with ID: {order_id}")

    def _cancel_orders(self):
        if self._orders:
            self._logger.info(f"Cancelling {len(self._orders)} orders: {self._orders}")
            self._client.cancel_orders(self._orders)
            self._orders = []
        else:
            self._logger.debug("No orders to cancel")

    def trading_loop(self):
        self._logger.info("Starting trading loop")
        try:
            yes_bid, no_bid = self._find_order_prices()
            if yes_bid <= 0.02 or yes_bid >= 0.95 or no_bid <= 0.02 or no_bid >= 0.95:
                self._logger.warning(f"Prices out of bounds - Yes: {yes_bid:.3f}, No: {no_bid:.3f}. Stopping.")
                self._cancel_orders()
                # TODO: Make it sell off instead of just breaking
                return

            filled_order = self._client.check_orders_filled(self._orders)

            if not self._orders:
                self._logger.info("No active orders, placing new orders")
                self._place_orders(yes_bid, no_bid)
            elif filled_order:
                self._logger.info(f"Orders filled: {filled_order}")
                self._cancel_orders()
            elif (
                # Only replace orders if the price difference is significant
                # AND not just our own order getting filled
                (abs(yes_bid - self._prev_yes_bid) > self._tick_size * 2 and not self._orders)
                or
                (abs(no_bid - self._prev_no_bid) > self._tick_size * 2 and not self._orders)
            ):
                self._logger.info(
                    f"Price change detected - "
                    f"Yes: {self._prev_yes_bid:.3f} -> {yes_bid:.3f}, "
                    f"No: {self._prev_no_bid:.3f} -> {no_bid:.3f}"
                )
                self._cancel_orders()
                self._place_orders(yes_bid, no_bid)

            self._prev_yes_bid = yes_bid
            self._prev_no_bid = no_bid

            time.sleep(3)
        except Exception as e:
            self._logger.error(f"Error in trading loop: {e}", exc_info=True)
            time.sleep(5)  # Wait a bit longer on error before retrying
