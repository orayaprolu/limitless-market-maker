from dataclasses import dataclass
import os
from dotenv import load_dotenv
from models.constants import DEFAULT_LOG_LEVEL, STRATEGY_LOG_LEVEL, INFO_LOG_LEVEL, LOG_FORMAT

load_dotenv()

@dataclass
class DeribitConfig:
    lower_instrument_earlier: str
    upper_instrument_later: str
    lower_instrument_later: str
    upper_instrument_earlier: str
    target_instrument: str

@dataclass
class StrategyConfig:
    market_id: str
    deribit_config: DeribitConfig
    allocation: float

# Strategy configurations
STRATEGY_CONFIGS = [
    StrategyConfig(
        market_id="dollarbtc-above-dollar10729842-on-sep-1-1000-utc-1756116049862",
        deribit_config=DeribitConfig(
            lower_instrument_earlier='BTC-30AUG25-106000-C',
            upper_instrument_later='BTC-30AUG25-108000-C',
            lower_instrument_later='BTC-5SEP25-106000-C',
            upper_instrument_earlier='BTC-5SEP25-108000-C',
            target_instrument="BTC-1SEP25-107298-C"
        ),
        allocation=50
    ),
    StrategyConfig(
        market_id="dollarbtc-above-dollar10953381-on-sep-1-1000-utc-1756116084638",
        deribit_config=DeribitConfig(
            lower_instrument_earlier='BTC-30AUG25-109000-C',
            upper_instrument_later='BTC-30AUG25-110000-C',
            lower_instrument_later='BTC-5SEP25-109000-C',
            upper_instrument_earlier='BTC-5SEP25-110000-C',
            target_instrument="BTC-1SEP25-109533-C"
        ),
        allocation=50
    ),
    StrategyConfig(
        market_id="dollarbtc-above-dollar11176919-on-sep-1-1000-utc-1756116121021",
        deribit_config=DeribitConfig(
            lower_instrument_earlier='BTC-30AUG25-111000-C',
            upper_instrument_later='BTC-30AUG25-112000-C',
            lower_instrument_later='BTC-5SEP25-111000-C',
            upper_instrument_earlier='BTC-5SEP25-112000-C',
            target_instrument="BTC-1SEP25-111769-C"
        ),
        allocation=50
    )
]

# Environment settings
PRIVATE_KEY = os.getenv('PRIVATE_KEY') or ""

# Logging configuration
LOGGING_CONFIG = {
    'level': INFO_LOG_LEVEL,
    'format': LOG_FORMAT,
    'strategy_level': STRATEGY_LOG_LEVEL
}
