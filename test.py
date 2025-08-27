from models.marketdata import MarketData
from proxies.limitless_proxy import LimitlessProxy
from clients.limitless_client import LimitlessClient
from strategy.reward_farmer import RewardFarmer
from datastreams.limitless_datastream import LimitlessDatastream
from datastreams.deribit_datastream import DeribitDatastream
from dotenv import load_dotenv
from eth_account import Account
import os
from pprint import pprint
import time
import logging

# Set up logging to only show strategy engine logs
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Set strategy logger to DEBUG level
logging.getLogger('strategy.reward_farmer').setLevel(logging.DEBUG)

load_dotenv()
account = Account.from_key(os.getenv("PRIVATE_KEY"))
private_key = os.getenv('PRIVATE_KEY') or ""

client = LimitlessClient(private_key)
market_data = client.get_market_data("dollarbtc-above-dollar10729842-on-sep-1-1000-utc-1756116049862")
limitless_datastream = LimitlessDatastream(client, market_data)
deribit_datastream = DeribitDatastream(
    lower_instrument_earlier='BTC-29AUG25-106000-C',
    upper_instrument_later='BTC-29AUG25-108000-C',
    lower_instrument_later='BTC-5SEP25-106000-C',
    upper_instrument_earlier='BTC-5SEP25-108000-C',
    target_instrument="BTC-1SEP25-107298-C"
)
strategy = RewardFarmer(client, limitless_datastream, deribit_datastream, 50, market_data)

while True:
    deribit_datastream._update_prices()
    print('updated deribit_datastream')
    limitless_datastream._update_bba()
    print('updated limitless_datastream')
    strategy.trading_loop()
    print('finished trading loop')

    # bba = datastream.get_bba()
    # target_price = deribit_datastream.get_target_price()
    # print(bba)
    # print(target_price)
    # time.sleep(3)

    # prices = strategy._find_order_prices()
    # print(prices)
    # time.sleep(3)



# order = proxy.place_order(0.44, 20, 'YES', 'SELL', market_data)
# id = order['order']['id']
# print(order, id)
# print('done, should wait 5 second now')
# print(proxy.cancel_order(str(id)))

yes_shares, no_shares = client.get_position(market_data)
pprint(yes_shares)
pprint(no_shares)
