from proxies.limitless_proxy import LimitlessProxy
from clients.limitless_client import LimitlessClient
from strategy.reward_farmer import RewardFarmer
from datastreams.limitless_datastream import LimitlessDatastream
from datastreams.deribit_datastream import DeribitDatastream
from config.strategy_config import STRATEGY_CONFIGS, PRIVATE_KEY, LOGGING_CONFIG
from utils.colored_logging import get_market_logger, get_market_name, setup_root_logger
from eth_account import Account
import logging
import time

# Configure logging
setup_root_logger(LOGGING_CONFIG['level'], LOGGING_CONFIG['format'])
logging.getLogger('strategy.reward_farmer').setLevel(
    getattr(logging, LOGGING_CONFIG['strategy_level'])
)

class StrategyManager:
    def __init__(self, private_key: str):
        self.private_key = private_key
        self.account = Account.from_key(private_key)
        self.proxy = LimitlessProxy(private_key)
        self.strategies = []
        self.clients = []
        self.limitless_datastreams = []
        self.deribit_datastreams = []

    def initialize_strategies(self):
        """Initialize all strategies from configuration"""
        for i, config in enumerate(STRATEGY_CONFIGS):
            market_logger = get_market_logger(config.market_id, i)
            market_name = get_market_name(config.market_id)
            print(f"Initializing {market_name}: {config.market_id}")

            # Create client
            client = LimitlessClient(self.private_key, self.proxy)
            market_data = client.get_market_data(config.market_id)

            # Create datastreams
            limitless_datastream = LimitlessDatastream(client, market_data)
            deribit_datastream = DeribitDatastream(
                lower_instrument_earlier=config.deribit_config.lower_instrument_earlier,
                upper_instrument_later=config.deribit_config.upper_instrument_later,
                lower_instrument_later=config.deribit_config.lower_instrument_later,
                upper_instrument_earlier=config.deribit_config.upper_instrument_earlier,
                target_instrument=config.deribit_config.target_instrument
            )

            # Create strategy with custom logger
            strategy = RewardFarmer(
                client,
                limitless_datastream,
                deribit_datastream,
                config.allocation,
                market_data,
                custom_logger=market_logger
            )

            # Store references
            self.clients.append(client)
            self.limitless_datastreams.append(limitless_datastream)
            self.deribit_datastreams.append(deribit_datastream)
            self.strategies.append(strategy)

            print(f"{market_name} initialized successfully")

    def run_trading_loop(self):
        """Main trading loop for all strategies"""
        print("Starting trading loop...")

        while True:
            try:
                for i, (strategy, deribit_ds, limitless_ds, config) in enumerate(
                    zip(self.strategies, self.deribit_datastreams, self.limitless_datastreams, STRATEGY_CONFIGS)
                ):
                    market_name = get_market_name(config.market_id)
                    print(f"Running {market_name}...")

                    # Update data streams
                    deribit_ds.update_prices()
                    limitless_ds.update_bba()

                    # Execute trading logic
                    strategy.trading_loop()

                    print(f"Finished {market_name} loop")

                print("Finished all strategies")
                print("-" * 50)

            except KeyboardInterrupt:
                print("Trading loop interrupted by user")
                break
            except Exception as e:
                print(f"Error in trading loop: {e}")
                logging.error(f"Trading loop error: {e}")
                time.sleep(5)  # Wait before retrying

    def get_positions_summary(self):
        """Get position summary for all strategies"""
        print("\nPosition Summary:")
        print("=" * 60)

        for i, (client, config) in enumerate(zip(self.clients, STRATEGY_CONFIGS)):
            try:
                market_name = get_market_name(config.market_id)
                market_data = client.market_data if hasattr(client, 'market_data') else None
                if market_data:
                    yes_shares, no_shares = client.get_position(market_data)
                    print(f"{market_name}:")
                    print(f"  YES shares: {yes_shares}")
                    print(f"  NO shares: {no_shares}")
                    print("-" * 40)
            except Exception as e:
                market_name = get_market_name(config.market_id)
                print(f"  Error getting position for {market_name}: {e}")

def main():
    """Main function to run the trading system"""
    print("Initializing Limitless Market Maker...")

    if not PRIVATE_KEY:
        print("ERROR: PRIVATE_KEY environment variable not set")
        return

    # Create strategy manager
    manager = StrategyManager(PRIVATE_KEY)

    # Initialize all strategies
    manager.initialize_strategies()

    # Get initial position summary
    manager.get_positions_summary()

    # Start trading loop
    try:
        manager.run_trading_loop()
    except Exception as e:
        print(f"Fatal error: {e}")
        logging.error(f"Fatal error in main: {e}")
    finally:
        # Get final position summary
        manager.get_positions_summary()
        print("Trading system shutdown complete")

if __name__ == "__main__":
    main()
