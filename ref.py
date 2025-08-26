# strategy_engine.py
from __future__ import annotations

import threading
import time
import traceback

from typing import Optional, Tuple

from order_manager import LimitlessOrderManager
from limitless_data_stream import LimitlessBookStream, BestQuotes
from deribit_stream import DeribitBinaryInterpStream, BinaryInterpSnapshot
from snap import safe_snap_up, safe_snap_down
import datetime
import sys
from dotenv import load_dotenv

load_dotenv()


def log(msg: str):
    """Simple timestamped logger for the main loop."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stdout, flush=True)


class StrategyEngine:
    """
    Runs:
      - Limitless YES/NO book stream
      - Deribit binary-price interpolation stream (low/high -> target)
      - Background trading loop that does place/replace until stopped
    """

    def __init__(
        self,
        slug: str,
        yes_asset_id: str,
        no_asset_id: str,
        usd_order_amount: float,
        usd_bba_limit_ratio: float = 1.5,
        usd_order_limit_ratio: float = 3,

        # Deribit config (four instruments for two-step interpolation)
        deribit_lower_instrument_earlier_expiration: Optional[str] = None,
        deribit_upper_instrument_earlier_expiration: Optional[str] = None,
        deribit_lower_instrument_later_expiration: Optional[str] = None,
        deribit_upper_instrument_later_expiration: Optional[str] = None,
        deribit_target_strike: Optional[float] = None,

        # trading knobs
        tick_size: float = 0.001,
        sell_only: bool = False
    ):
        self.slug = slug
        self.yes_asset_id = yes_asset_id
        self.no_asset_id = no_asset_id
        self.usd_order_amount = float(usd_order_amount)
        self.usd_bba_limit_ratio = float(usd_bba_limit_ratio)
        self.usd_order_limit_ratio = float(usd_order_limit_ratio)
        self.tick_size = float(tick_size)

        self.order_manager = LimitlessOrderManager(slug, yes_asset_id, no_asset_id)
        self.sell_only = sell_only

        # Thread-safe state
        self._lock = threading.RLock()

        # Limitless quotes
        self.yes_bid: Optional[float] = None
        self.yes_ask: Optional[float] = None
        self.no_bid: Optional[float] = None
        self.no_ask: Optional[float] = None
        self.max_half_spread: float = 0.03  # <- from BestQuotes
        self.max_spread: float = self.max_half_spread * 2

        # Position tracking (now fetched from account)
        self.yes_position: float = 0.0  # Net YES position (USD value) - cached
        self.no_position: float = 0.0   # Net NO position (USD value) - cached

        # Deribit binary interpolation
        self.deribit_lower_price: Optional[float] = None
        self.deribit_upper_price: Optional[float] = None
        self.deribit_target_price: Optional[float] = None
        self.deribit_lower_strike: Optional[float] = None
        self.deribit_upper_strike: Optional[float] = None

        # Streams
        self.limitless_stream = LimitlessBookStream(
            slug=self.slug,
            api_base="https://api.limitless.exchange",
            on_update=self._on_limitless_update,
        )

        self.deribit_interp_stream: Optional[DeribitBinaryInterpStream] = None
        if (deribit_lower_instrument_earlier_expiration and deribit_upper_instrument_earlier_expiration and
            deribit_lower_instrument_later_expiration and deribit_upper_instrument_later_expiration and
            deribit_target_strike is not None):
            self.deribit_interp_stream = DeribitBinaryInterpStream(
                lower_instrument_earlier=deribit_lower_instrument_earlier_expiration,
                upper_instrument_earlier=deribit_upper_instrument_earlier_expiration,
                lower_instrument_later=deribit_lower_instrument_later_expiration,
                upper_instrument_later=deribit_upper_instrument_later_expiration,
                target_strike=float(deribit_target_strike),
                on_update=self._on_deribit_interp_update,
            )

        # trading loop internals
        self._trade_thread: Optional[threading.Thread] = None
        self._trade_stop = threading.Event()
        self._last_yes_bid: Optional[float] = None
        self._last_no_bid: Optional[float] = None
        self._last_place_ts: float = 0.0

    # ---- stream callbacks ----
    def _on_limitless_update(self, quotes: BestQuotes):
        with self._lock:
            self.yes_bid, self.yes_ask = quotes.yes_bid, quotes.yes_ask
            self.no_bid, self.no_ask = quotes.no_bid, quotes.no_ask
            # if quotes.max_half_spread is not None:
            #     self.max_half_spread = quotes.max_half_spread

    def _on_deribit_interp_update(self, s: BinaryInterpSnapshot):
        with self._lock:
            self.deribit_lower_price = s.lower_price
            self.deribit_upper_price = s.upper_price
            self.deribit_target_price = s.target_price
            self.deribit_lower_strike = s.lower_strike
            self.deribit_upper_strike = s.upper_strike

    # ---- lifecycle ----
    def start(self):
        self.limitless_stream.start()
        if self.deribit_interp_stream:
            self.deribit_interp_stream.start()

    def stop(self):
        self.stop_trading()
        self.limitless_stream.stop()
        if self.deribit_interp_stream:
            self.deribit_interp_stream.stop()

    # ---- background trading loop control ----
    def start_trading(self):
        if self._trade_thread and self._trade_thread.is_alive():
            return
        self._trade_stop.clear()
        self._trade_thread = threading.Thread(target=self._trading_loop, daemon=True)
        self._trade_thread.start()

    def stop_trading(self):
        self._trade_stop.set()
        if self._trade_thread:
            self._trade_thread.join(timeout=2)

    def update_positions_from_account(self):
        """
        Fetch current positions from the account via the order manager.
        Updates the cached yes_position and no_position values.
        """
        try:
            portfolio = self.order_manager.get_portfolio()
            if not portfolio:
                log("No portfolio data available")
                return



            # Parse portfolio response according to PortfolioPositionsDto schema
            # The API returns: { "clob": [...], "amm": [...], "rewards": {...} }
            yes_found = False
            no_found = False

            # Helper function to extract position value from market position data
            def extract_position_value(position_data):
                """Extract USD value from position data"""
                if isinstance(position_data, dict):
                    # According to API schema, positions have marketValue field
                    # Values appear to be in smallest units (6 decimals for USDC)
                    USDC_DECIMALS = 1000000  # 10^6 for USDC

                    market_value = position_data.get('marketValue', 0)
                    if market_value:
                        # Convert from smallest units to dollars
                        return float(market_value) / USDC_DECIMALS

                    # Fallback to cost if marketValue not available
                    cost = position_data.get('cost', 0)
                    if cost:
                        return float(cost) / USDC_DECIMALS

                    # Try tokensBalance field for CLOB positions
                    tokens = position_data.get('tokensBalance', 0)
                    if tokens:
                        # Tokens are in smallest units, convert and multiply by estimated price
                        return (float(tokens) / USDC_DECIMALS) * 0.05  # Default 5 cents per share
                return 0.0

            # Check if this is a PortfolioPositionsDto response
            if isinstance(portfolio, dict) and 'clob' in portfolio:
                # Process CLOB positions (this is where YES/NO tokens are)
                clob_positions = portfolio.get('clob', [])


                for clob_position in clob_positions:
                    # Each CLOB position has a market and positions object
                    market = clob_position.get('market', {})
                    market_slug = market.get('slug', '')

                    # Check if this is our market
                    if market_slug == self.slug:

                        positions = clob_position.get('positions', {})

                        # positions should have 'yes' and 'no' fields according to MarketPositionDataDto
                        if 'yes' in positions:
                            self.yes_position = extract_position_value(positions['yes'])
                            yes_found = True
                            log(f"Found YES position: ${self.yes_position:.2f}")

                        if 'no' in positions:
                            self.no_position = extract_position_value(positions['no'])
                            no_found = True
                            log(f"Found NO position: ${self.no_position:.2f}")

                        # Also check tokensBalance if positions not detailed
                        if not yes_found and not no_found:
                            tokens_balance = clob_position.get('tokensBalance', {})
                            if isinstance(tokens_balance, dict):
                                # Check if token IDs are in the balance dict
                                USDC_DECIMALS = 1000000  # 10^6 for USDC
                                if str(self.yes_asset_id) in tokens_balance:
                                    self.yes_position = (float(tokens_balance[str(self.yes_asset_id)]) / USDC_DECIMALS) * 0.05
                                    yes_found = True
                                    log(f"Found YES position from tokensBalance: ${self.yes_position:.2f}")
                                if str(self.no_asset_id) in tokens_balance:
                                    self.no_position = (float(tokens_balance[str(self.no_asset_id)]) / USDC_DECIMALS) * 0.05
                                    no_found = True
                                    log(f"Found NO position from tokensBalance: ${self.no_position:.2f}")

            # Fallback to simple list format if not PortfolioPositionsDto
            elif isinstance(portfolio, list):
                for item in portfolio:
                    # Simple position format
                    market = item.get('market', {})
                    if market.get('slug') == self.slug:
                        positions = item.get('positions', {})
                        if 'yes' in positions:
                            self.yes_position = extract_position_value(positions['yes'])
                            yes_found = True
                        if 'no' in positions:
                            self.no_position = extract_position_value(positions['no'])
                            no_found = True

            if not yes_found:
                self.yes_position = 0.0
                log(f"YES asset {self.yes_asset_id[:20]}... not found in portfolio, defaulting to $0.00")
            if not no_found:
                self.no_position = 0.0
                log(f"NO asset {self.no_asset_id[:20]}... not found in portfolio, defaulting to $0.00")

            log(f"Final positions - YES: ${self.yes_position:.2f}, NO: ${self.no_position:.2f}")

        except Exception as e:
            log(f"Error updating positions from account: {e}")
            # Don't raise, just keep current positions
            log(f"Keeping current positions - YES: ${self.yes_position:.2f}, NO: ${self.no_position:.2f}")

    # ---- snapshot for your strategy loop / logging ----
    def snapshot(self) -> dict:
        with self._lock:
            band = self.deribit_rewards_band()

            # Get reward pool info from latest quotes
            latest_quotes = self.limitless_stream.latest()
            reward_info = latest_quotes.reward_pool_info if latest_quotes else None

            # Calculate reward share for current position size
            reward_share = None
            if latest_quotes and self.usd_order_amount:
                # Estimate total position (YES + NO orders)
                estimated_position = self.usd_order_amount * 2  # Both YES and NO
                reward_share = self.limitless_stream.calculate_reward_share(estimated_position)

            return {
                "limitless": {
                    "yes_bid": self.yes_bid,
                    "yes_ask": self.yes_ask,
                    "no_bid": self.no_bid,
                    "no_ask": self.no_ask,
                    "max_half_spread": self.max_half_spread,
                },
                "deribit": {
                    "lower_strike": self.deribit_lower_strike,
                    "upper_strike": self.deribit_upper_strike,
                    "lower_price": self.deribit_lower_price,
                    "upper_price": self.deribit_upper_price,
                    "target_price": self.deribit_target_price,
                    "rewards_band": band,
                },
                "rewards": {
                    "pool_info": reward_info,
                    "estimated_share": reward_share,
                },
                "positions": {
                    "yes_position": self.yes_position,
                    "no_position": self.no_position,
                    "net_position": self.yes_position - self.no_position,
                    "total_exposure": abs(self.yes_position) + abs(self.no_position),
                    "active_orders":self.order_manager.active_orders
                },
            }

    # ---- pricing helpers ----
    def deribit_rewards_band(self) -> Optional[tuple[float, float]]:
        """
        Returns (low, high) = (target_price - max_half_spread, target_price + max_half_spread),
        clamped to [0, 1]. Uses Limitless max_half_spread and Deribit target price.
        """
        with self._lock:
            p = self.deribit_target_price
            h = self.max_half_spread
        if p is None or h is None:
            return None
        lo = max(0.0, p - h)
        hi = min(1.0, p + h)
        return (lo, hi)

    def _find_order_prices(self) -> Tuple[Optional[float], Optional[float]]:
        band = self.deribit_rewards_band()
        if not band:
            return None, None
        lower_band, upper_band = band
        if lower_band is None or upper_band is None or not self.deribit_target_price:
            return None, None

        # YES bid at lower edge; NO bid reflects 1 - upper edge
        target_yes_bid = lower_band
        target_no_bid = 1.0 - upper_band

        max_yes_bid = target_yes_bid + (self.max_half_spread / 2)
        max_no_bid = target_no_bid + (self.max_half_spread / 2)

        # zero/None guard
        if target_yes_bid is not None and target_yes_bid <= 0.0:
            target_yes_bid = None
        if target_no_bid is not None and target_no_bid <= 0.0:
            target_no_bid = None

        # Get current market bids (thread-safe)
        with self._lock:
            current_yes_bid = self.yes_bid
            current_no_bid = self.no_bid
            current_yes_ask = self.yes_ask
            current_no_ask = self.no_ask

        if not current_yes_bid or not current_yes_ask or not current_no_bid or not current_no_ask:
            return None, None

        midprice = (current_yes_bid + current_yes_ask) / 2
        spread = current_yes_ask - current_yes_bid
        true_lower_bound = midprice - self.max_half_spread
        true_upper_bound = midprice + self.max_half_spread

        print("LOOK HERE", target_yes_bid, max_yes_bid, current_yes_bid)
        ret_yes_bid = self._calculate_competitive_bid(
            target_yes_bid, max_yes_bid, current_yes_bid,
            spread, true_lower_bound
        )
        ret_no_bid = self._calculate_competitive_bid(
            target_no_bid, max_no_bid, current_no_bid,
            spread, 1 - true_upper_bound
        )

        inventory_difference = self.yes_position - self.no_position
        if inventory_difference > self.usd_order_amount * self.usd_bba_limit_ratio:
            print("too much yes inventory, decreasing bid to end of rewards band")
            ret_yes_bid = lower_band

        elif inventory_difference < -self.usd_order_amount * self.usd_bba_limit_ratio:
            print("too much no inventory, decreasing bid to end of rewards band")
            ret_no_bid = 1 - upper_band

        over_yes_share_threshold = inventory_difference >= self.usd_order_amount * self.usd_order_limit_ratio
        over_no_share_threshold = inventory_difference <= -self.usd_order_amount * self.usd_order_limit_ratio

        if over_yes_share_threshold:
            print("over yes inventory threshold, setting no bid to target and yes bid max_spread under")
            ret_no_bid = 1 - self.deribit_target_price
            if spread < self.max_spread:
                print(f'spread is less than {self.max_spread}')
                ret_yes_bid = midprice - self.max_half_spread
            else:
                print(f'spread is greater than {self.max_spread}')
                ret_yes_bid = self.deribit_target_price - self.max_spread

        if over_no_share_threshold:
            print("over no inventory threshold, setting yes bid to target and no bid max_spread under")
            ret_yes_bid = self.deribit_target_price
            if spread < self.max_spread:
                print(f'spread is less than {self.max_spread}')
                ret_no_bid = (1 - midprice) - self.max_half_spread
            else:
                print(f'spread is greater than {self.max_spread}')
                ret_no_bid = (1 - self.deribit_target_price) - self.max_spread

        if not ret_yes_bid or ret_yes_bid < 0:
            ret_yes_bid = self.tick_size

        if not ret_no_bid or ret_no_bid < 0:
            ret_no_bid = self.tick_size

        return safe_snap_up(ret_yes_bid, self.tick_size), safe_snap_up(ret_no_bid, self.tick_size)

    def _calculate_competitive_bid(self, target_bid: Optional[float], max_bid: float,
                                  current_market_bid: Optional[float],
                                  spread: float, lower_bound: float) -> Optional[float]:
        """Simple competitive bidding: chase BBA up to max value."""
        if not target_bid or not max_bid:
            return None

        current_market_bid = float(current_market_bid if current_market_bid else 0)
        print('CURRENT MARKET BID', current_market_bid)
        print('MAX_BID', max_bid)
        print('TARGET_BID', target_bid)

        # If best bid is under reward band just set order at reward band
        if current_market_bid < target_bid:
            bid = target_bid
        # If best bid is over max bid just set order at max bid
        elif current_market_bid + self.tick_size > max_bid:
            bid = max_bid
        # otherwise set order right above best bid
        else:
            bid = current_market_bid + self.tick_size

        print('SPREAD', spread)
        print('BID', bid)
        print('LOWER BOUND', lower_bound)

        if spread <= self.max_spread:
            bid = max(bid, lower_bound)

        print('FINAL BID', bid)
        return safe_snap_up(bid, self.tick_size)

    # ---- order placement ----

    def _sell_inventory_only(self, yes_bid: float, no_bid: float):
        """Sell-only mode: liquidate positions when target price is too extreme."""
        # Sell YES position if we have one and there's a bid
        if self.yes_position > 0 and no_bid is not None:
            yes_ask = safe_snap_down(1 - no_bid, self.tick_size)
            log(f"Selling YES position: ${self.yes_position:.2f} at {yes_ask:.3f}")
            sell_yes = self.order_manager.sell_yes(yes_ask, self.yes_position)
            if not sell_yes:
                log(f"Failed to sell YES position at {yes_ask}")

        # Sell NO position if we have one and there's a bid
        if self.no_position > 0 and yes_bid is not None:
            no_ask = safe_snap_down(1 - yes_bid, self.tick_size)
            log(f"Selling NO position: ${self.no_position:.2f} at {no_ask:.3f}")
            sell_no = self.order_manager.sell_no(no_ask, self.no_position)
            if not sell_no:
                log(f"Failed to sell NO position at {no_ask}")

        # Check if we've liquidated everything
        if self.yes_position <= 1.0 and self.no_position <= 1.0:
            log("All positions liquidated, exiting sell-only mode")
            self.sell_only = False

    def _place_orders(self, yes_bid: float, no_bid: float):
        """Place market-making orders or liquidate inventory if in sell-only mode."""
        try:
            self.update_positions_from_account()
        except Exception as e:
            log(f"Could not update positions after order placement: {e}")

        if self.sell_only:
            # Sell-only mode: liquidate positions at current market prices
            self._sell_inventory_only(yes_bid, no_bid)
            return

        usd_order_amount = self.usd_order_amount
        print('USD ORDER AMOUNT', usd_order_amount)

        # Normal trading mode
        sell_yes = None
        if self.yes_position >= usd_order_amount and no_bid is not None:
            yes_ask = safe_snap_down(1 - no_bid, self.tick_size)
            sell_yes = self.order_manager.sell_yes(yes_ask, abs(usd_order_amount))
            if not sell_yes:
                log(f"Failed to place sell_yes order at {yes_ask}")

        sell_no = None
        if self.no_position >= usd_order_amount and yes_bid is not None:
            no_ask = safe_snap_down(1 - yes_bid, self.tick_size)
            sell_no = self.order_manager.sell_no(no_ask, abs(usd_order_amount))
            if not sell_no:
                log(f"Failed to place sell_no order at {no_ask}")

        if yes_bid is not None:
            buy_yes = self.order_manager.buy_yes(yes_bid, abs(usd_order_amount))
            if not buy_yes:
                log(f"Failed to place buy_yes order at {yes_bid}")
        if no_bid is not None:
            buy_no = self.order_manager.buy_no(no_bid, abs(usd_order_amount))
            if not buy_no:
                log(f"Failed to place buy_no order at {no_bid}")

    # ---- trading loop ----
    def _trading_loop(self):
        log("Starting trading loop")
        prev_yes_bid = None
        prev_no_bid = None
        last_position_update = 0

        while not self._trade_stop.is_set():
            try:
                # Periodically refresh positions from account (every 2 minutes)
                current_time = time.time()
                if current_time - last_position_update > 120:
                    try:
                        self.update_positions_from_account()
                        last_position_update = current_time
                    except Exception as e:
                        log(f"Periodic position update failed: {e}")
                        # Don't update last_position_update so we'll try again soon

                order_prices = self._find_order_prices()

                if not order_prices:
                    log("No order prices found")
                    self._trade_stop.wait(30)
                    continue
                yes_bid, no_bid = order_prices
                yes_str = f"{yes_bid:.3f}" if yes_bid is not None else "None"
                no_str = f"{no_bid:.3f}" if no_bid is not None else "None"
                log(f"Target Order prices: YES {yes_str}, NO {no_str}")

                if not yes_bid or not no_bid:
                    log("No order prices found")
                    self._trade_stop.wait(30)
                    continue

                if yes_bid <= 0.02 or yes_bid >= 0.95 or no_bid <= 0.02 or no_bid >= 0.95:
                    log("Invalid order prices, entering sell-only mode...")
                    self.order_manager.cancel_active_orders()
                    self.sell_only = True

                if self.sell_only:
                    log("Selling inventory only!")
                    self._place_orders(yes_bid, no_bid)
                    continue

                if not self.order_manager.has_active_orders():
                    if yes_bid is not None and no_bid is not None:
                        log(f"Placing orders: YES {yes_bid:.3f}, NO {no_bid:.3f}")
                        self._place_orders(yes_bid, no_bid)
                    else:
                        log(f"Cannot place orders - invalid prices: YES {yes_str}, NO {no_str}")

                elif self.order_manager.check_orders_filled():
                    log("Order filled detected - canceling and replacing orders")
                    self.order_manager.cancel_active_orders()
                    self._trade_stop.wait(5)
                    self._place_orders(yes_bid, no_bid)

                elif yes_bid != prev_yes_bid or no_bid != prev_no_bid:
                    # Price changed - replace orders
                    log("Price changed - replacing orders:")

                    yes_change = None
                    no_change = None

                    if prev_yes_bid is not None and yes_bid is not None:
                        yes_change = abs(yes_bid - prev_yes_bid)
                        log(f"  YES: {prev_yes_bid:.3f} → {yes_bid:.3f} (Δ{yes_change:.4f})")
                    else:
                        prev_yes_str = f"{prev_yes_bid:.3f}" if prev_yes_bid is not None else "None"
                        curr_yes_str = f"{yes_bid:.3f}" if yes_bid is not None else "None"
                        log(f"  YES: {prev_yes_str} → {curr_yes_str}")

                    if prev_no_bid is not None and no_bid is not None:
                        no_change = abs(no_bid - prev_no_bid)
                        log(f"  NO:  {prev_no_bid:.3f} → {no_bid:.3f} (Δ{no_change:.4f})")
                    else:
                        prev_no_str = f"{prev_no_bid:.3f}" if prev_no_bid is not None else "None"
                        curr_no_str = f"{no_bid:.3f}" if no_bid is not None else "None"
                        log(f"  NO:  {prev_no_str} → {curr_no_str}")

                    if not yes_change or not no_change:
                        self._trade_stop.wait(30)
                        continue

                    # if 0.001 tick size only shift in 0.003 increments or more
                    max_change = max(yes_change, no_change)
                    print(f"Max change: {max_change}")
                    if self.tick_size == 0.001 and max_change < 0.003:
                        self._trade_stop.wait(30)
                        continue

                    if yes_bid is not None and no_bid is not None:
                        self.order_manager.cancel_active_orders()
                        self._trade_stop.wait(5)
                        self._place_orders(yes_bid, no_bid)

                prev_yes_bid = yes_bid
                prev_no_bid = no_bid

                self._trade_stop.wait(30)

            except Exception as e:
                    # or, if you don’t use logging:
                print("Trading loop error:\n", traceback.format_exc())
                self._trade_stop.wait(10)


if __name__ == "__main__":
    engine = StrategyEngine(
        slug="dollarbtc-above-dollar11890254-on-aug-18-1000-utc-1754907845530",
        yes_asset_id="19006194790511586866405053334413708941648239952738100332032301345925246674412",
        no_asset_id="8274771340273773182180515566380622609744281270025421036381966689275905016568",
        usd_order_amount=50,
        deribit_lower_instrument="BTC-18AUG25-118000-C",
        deribit_upper_instrument="BTC-18AUG25-119000-C",
        deribit_target_strike= 118_902.54,
    )

    engine.start()
    print("Warming up Strategy Engine data collection...")
    time.sleep(30)

    # kick off continuous place/replace in the background
    engine.start_trading()

    try:
        while True:
            snap = engine.snapshot()
            log("=== Limitless Quotes ===")
            log(f"YES bid: {snap['limitless']['yes_bid']} | YES ask: {snap['limitless']['yes_ask']}")
            log(f"NO  bid: {snap['limitless']['no_bid']}  | NO  ask: {snap['limitless']['no_ask']}")
            log(f"max_half_spread: {snap['limitless']['max_half_spread']}")
            log("=== Deribit Binary Prices ===")
            log(f"Lower strike: {snap['deribit']['lower_strike']} | Price: {snap['deribit']['lower_price']}")
            log(f"Upper strike: {snap['deribit']['upper_strike']} | Price: {snap['deribit']['upper_price']}")
            tp = snap['deribit']['target_price']
            band = snap['deribit']['rewards_band']
            log(f"Target strike: {engine.deribit_interp_stream.target_strike if engine.deribit_interp_stream else None} "
                f"| Target price: {tp}")
            if band is not None:
                log(f"==> Rewards band around Deribit target: [{band[0]:.6f}, {band[1]:.6f}]")
            else:
                log("==> Rewards band: (waiting for data)")

            # Display reward pool information
            reward_info = snap['rewards']['pool_info']
            reward_share = snap['rewards']['estimated_share']

            if reward_info and reward_info.get('is_rewardable'):
                log("=== Reward Pool Info ===")
                log(f"Market Volume: ${reward_info.get('volume', 0):,.2f}")
                log(f"Daily Reward Pool: ${reward_info.get('daily_reward', 0)}")
                log(f"Rewards Epoch: {reward_info.get('rewards_epoch', 0):.4f} days ({reward_info.get('rewards_epoch', 0) * 24:.1f}h)")

                if reward_share:
                    log(f"==> Your Est. Share: {reward_share['share_percentage']:.4f}%")
                    log(f"==> Est. Reward/Epoch: ${reward_share['reward_per_epoch']:.4f}")
                    log(f"==> Est. Daily Rate: ${reward_share['daily_reward_rate']:.4f}")
                else:
                    log("==> Reward share: calculating...")
            else:
                log("=== Reward Pool: Not available or not rewardable ===")

            # Display position info
            positions = snap['positions']
            log("=== Position Tracking ===")
            log(f"YES Position: ${positions['yes_position']:.2f}")
            log(f"NO Position:  ${positions['no_position']:.2f}")
            log(f"Net Position: ${positions['net_position']:.2f}")
            log(f"Total Exposure: ${positions['total_exposure']:.2f}")
            max_pos = 2 * abs(engine.usd_order_amount)
            log(f"Position Limit: ${max_pos:.2f} per side")
            print(f'Active Orders: {positions["active_orders"]}')

            log("-" * 50)
            time.sleep(45)
    except KeyboardInterrupt:
        log("Ctrl+C detected - cancelling all orders and shutting down...")
        try:
            result = engine.order_manager.cancel_active_orders()
            log(f"Orders cancelled: {result}")
        except Exception as e:
            log(f"Error cancelling orders: {e}")
    finally:
        engine.stop()
        log("Engine stopped")
