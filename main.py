from clients.limitless_client import LimitlessClient
from dotenv import load_dotenv
import os
load_dotenv()

def trading_loop(slugs: list[str]):
    private_key = os.getenv("PRIVATE_KEY") or ""
    client = LimitlessClient(private_key)

    while True:
        for slug in slugs:

            # Run the DataStream for that market
            # Replace the orders for that market
