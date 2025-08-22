from typing import Literal

from clients.limitless_client import LimitlessClient

class LimitlessDatastream:
    Market = Literal["YES", "NO"] # hardcoded from proxy, probably better way to handle this

    def __init__(self, client: LimitlessClient, slug: str):
        self._client = client
        self.slug = slug
        self.yes_token_id, self.no_token_id = self._client.get_token_ids(slug)

        self.yes_best_bid = None
        self.yes_best_ask = None
        self.no_best_bid = None
        self.no_best_ask = None
