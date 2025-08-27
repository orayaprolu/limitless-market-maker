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

proxy = LimitlessProxy(private_key)

# Strategy 1
client_1 = LimitlessClient(private_key, proxy)
market_data_1 = client_1.get_market_data("dollarbtc-above-dollar10729842-on-sep-1-1000-utc-1756116049862")
limitless_datastream_1 = LimitlessDatastream(client_1, market_data_1)
deribit_datastream_1 = DeribitDatastream(
    lower_instrument_earlier='BTC-30AUG25-106000-C',
    upper_instrument_later='BTC-30AUG25-108000-C',
    lower_instrument_later='BTC-5SEP25-106000-C',
    upper_instrument_earlier='BTC-5SEP25-108000-C',
    target_instrument="BTC-1SEP25-107298-C"
)
strategy_1 = RewardFarmer(client_1, limitless_datastream_1, deribit_datastream_1, 50, market_data_1)

# Strategy 2
client_2 = LimitlessClient(private_key, proxy)
market_data_2 = client_2.get_market_data("dollarbtc-above-dollar10953381-on-sep-1-1000-utc-1756116084638")
limitless_datastream_2 = LimitlessDatastream(client_2, market_data_2)
deribit_datastream_2 = DeribitDatastream(
    lower_instrument_earlier='BTC-30AUG25-109000-C',
    upper_instrument_later='BTC-30AUG25-110000-C',
    lower_instrument_later='BTC-5SEP25-109000-C',
    upper_instrument_earlier='BTC-5SEP25-110000-C',
    target_instrument="BTC-1SEP25-109533-C"
)
strategy_2 = RewardFarmer(client_2, limitless_datastream_2, deribit_datastream_2, 50, market_data_2)

# Strategy 3
client_3 = LimitlessClient(private_key, proxy)
market_data_3 = client_3.get_market_data("dollarbtc-above-dollar11176919-on-sep-1-1000-utc-1756116121021")
limitless_datastream_3 = LimitlessDatastream(client_3, market_data_3)
deribit_datastream_3 = DeribitDatastream(
    lower_instrument_earlier='BTC-30AUG25-111000-C',
    upper_instrument_later='BTC-30AUG25-112000-C',
    lower_instrument_later='BTC-5SEP25-111000-C',
    upper_instrument_earlier='BTC-5SEP25-112000-C',
    target_instrument="BTC-1SEP25-111769-C"
)
strategy_3 = RewardFarmer(client_3, limitless_datastream_3, deribit_datastream_3, 50, market_data_3)

while True:
    deribit_datastream_1.update_prices()
    limitless_datastream_1.update_bba()
    strategy_1.trading_loop()
    print('finished strategy 1 loop')

    deribit_datastream_2.update_prices()
    limitless_datastream_2.update_bba()
    strategy_2.trading_loop()
    print('finished strategy 2 loop')

    deribit_datastream_3.update_prices()
    limitless_datastream_3.update_bba()
    strategy_3.trading_loop()
    print('finished strategy 3 loop')

    print('finished all strategies')


# while True:
#     deribit_datastream.update_prices()
#     print('updated deribit_datastream')
#     limitless_datastream.update_bba()
#     print('updated limitless_datastream')
#     strategy.trading_loop()
#     print('finished trading loop')

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
