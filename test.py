from models.marketdata import MarketData
from proxies.limitless_proxy import LimitlessProxy
from dotenv import load_dotenv
from eth_account import Account
import os

load_dotenv()
account = Account.from_key(os.getenv("PRIVATE_KEY"))
private_key = os.getenv('PRIVATE_KEY')

proxy = LimitlessProxy(private_key)
market_data = MarketData(
    slug="dollarbtc-above-dollar11509843-on-aug-25-1000-utc-1755511340391",
    yes_token="38311112601597115954108731736674165177547667440882981632004232973700477060054",
    no_token="53948619578272912237162925404802617997488075040854895688260903325241067402930"
)
# order = proxy.place_order(0.44, 20, 'YES', 'SELL', market_data)
# id = order['order']['id']
# print(order, id)
# print('done, should wait 5 second now')
# print(proxy.cancel_order(str(id)))

port = proxy.get_portfolio_history()

print(port)
