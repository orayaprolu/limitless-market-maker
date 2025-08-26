from models.marketdata import MarketData
from proxies.limitless_proxy import LimitlessProxy
from clients.limitless_client import LimitlessClient
from datastreams.limitless_datastream import LimitlessDatastream
from datastreams.deribit_datastream import DeribitDatastream
from dotenv import load_dotenv
from eth_account import Account
import os
from pprint import pprint
import time

load_dotenv()
account = Account.from_key(os.getenv("PRIVATE_KEY"))
private_key = os.getenv('PRIVATE_KEY') or ""

client = LimitlessClient(private_key)
market_data = client.get_market_data("dollargoog-above-dollar20672-on-aug-29-2000-utc-1755892978348")
datastream = LimitlessDatastream(client, market_data)
deribit_datastream = DeribitDatastream(
    lower_instrument_earlier='BTC-29AUG25-106000-C',
    upper_instrument_later='BTC-29AUG25-108000-C',
    lower_instrument_later='BTC-5SEP25-106000-C',
    upper_instrument_earlier='BTC-5SEP25-108000-C',
    target_strike=107298
)

while True:
    # bba = datastream.get_bba()
    # print(bba)

    target_price = deribit_datastream.get_target_price()
    print(target_price)
    time.sleep(3)



# order = proxy.place_order(0.44, 20, 'YES', 'SELL', market_data)
# id = order['order']['id']
# print(order, id)
# print('done, should wait 5 second now')
# print(proxy.cancel_order(str(id)))

yes_shares, no_shares = client.get_position(market_data)
pprint(yes_shares)
pprint(no_shares)
