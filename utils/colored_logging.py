"""
Colored logging utility for market-specific loggers.
Provides colored console output and unique logger names for different strategies.
"""

import logging
import sys
from typing import Dict, Optional
from dataclasses import dataclass

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # Fallback ANSI color codes
    class Fore:
        RED = '\033[31m'
        GREEN = '\033[32m'
        YELLOW = '\033[33m'
        BLUE = '\033[34m'
        MAGENTA = '\033[35m'
        CYAN = '\033[36m'
        WHITE = '\033[37m'
        RESET = '\033[0m'

    class Style:
        BRIGHT = '\033[1m'
        RESET_ALL = '\033[0m'


@dataclass
class MarketColors:
    """Color scheme for a specific market"""
    primary: str
    secondary: str
    accent: str


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log messages based on market ID"""

    def __init__(self, market_colors: MarketColors, market_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.market_colors = market_colors
        self.market_name = market_name

        # Level-based colors
        self.level_colors = {
            logging.DEBUG: Fore.WHITE,
            logging.INFO: self.market_colors.primary,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.RED + Style.BRIGHT,
        }

    def format(self, record):
        # Get the color for this log level
        color = self.level_colors.get(record.levelno, Fore.WHITE)

        # Format the record normally first
        formatted = super().format(record)

        # Add market identifier and color
        market_prefix = f"[{self.market_colors.accent}{self.market_name}{Fore.RESET}]"
        colored_message = f"{market_prefix} {color}{formatted}{Fore.RESET}"

        return colored_message


class MarketLoggerManager:
    """Manages colored loggers for different markets"""

    # Predefined color schemes for different markets
    COLOR_SCHEMES = [
        MarketColors(primary=Fore.CYAN, secondary=Fore.BLUE, accent=Fore.CYAN + Style.BRIGHT),
        MarketColors(primary=Fore.GREEN, secondary=Fore.YELLOW, accent=Fore.GREEN + Style.BRIGHT),
        MarketColors(primary=Fore.MAGENTA, secondary=Fore.RED, accent=Fore.MAGENTA + Style.BRIGHT),
        MarketColors(primary=Fore.BLUE, secondary=Fore.CYAN, accent=Fore.BLUE + Style.BRIGHT),
        MarketColors(primary=Fore.YELLOW, secondary=Fore.GREEN, accent=Fore.YELLOW + Style.BRIGHT),
    ]

    def __init__(self):
        self.loggers: Dict[str, logging.Logger] = {}
        self.market_names: Dict[str, str] = {}
        self.color_index = 0

    def get_market_logger(self, market_id: str, strategy_index: Optional[int] = None) -> logging.Logger:
        """
        Get or create a colored logger for a specific market

        Args:
            market_id: The market identifier
            strategy_index: Optional index for the strategy (for naming)

        Returns:
            Configured logger with colored output
        """
        if market_id in self.loggers:
            return self.loggers[market_id]

        # Extract a shorter market name from the market ID
        market_name = self._extract_market_name(market_id, strategy_index)

        # Create logger with unique name
        logger_name = f"strategy.reward_farmer.{market_name.lower().replace(' ', '_')}"
        logger = logging.getLogger(logger_name)

        # Remove existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Create colored console handler
        console_handler = logging.StreamHandler(sys.stdout)

        # Get color scheme
        colors = self.COLOR_SCHEMES[self.color_index % len(self.COLOR_SCHEMES)]
        self.color_index += 1

        # Create colored formatter
        formatter = ColoredFormatter(
            market_colors=colors,
            market_name=market_name,
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Set level (will be overridden by root logger config)
        logger.setLevel(logging.DEBUG)

        # Store references
        self.loggers[market_id] = logger
        self.market_names[market_id] = market_name

        return logger

    def _extract_market_name(self, market_id: str, strategy_index: Optional[int] = None) -> str:
        """Extract a human-readable name from market ID"""
        if strategy_index is not None:
            base_name = f"S{strategy_index + 1}"
        else:
            base_name = "Market"

        # Try to extract meaningful info from market ID
        if "btc" in market_id.lower():
            # Extract price from BTC market IDs
            parts = market_id.split('-')
            for part in parts:
                if part.replace('dollar', '').replace('above', '').replace('below', '').isdigit():
                    price = part.replace('dollar', '')
                    if 'above' in part.lower():
                        return f"{base_name} BTC>${price[:3]}k"
                    elif 'below' in part.lower():
                        return f"{base_name} BTC<${price[:3]}k"

            # Fallback for BTC markets
            return f"{base_name} BTC"

        # Generic fallback
        return f"{base_name} Market"

    def get_market_name(self, market_id: str) -> str:
        """Get the display name for a market"""
        return self.market_names.get(market_id, "Unknown Market")


# Global instance
_market_logger_manager = MarketLoggerManager()


def get_market_logger(market_id: str, strategy_index: Optional[int] = None) -> logging.Logger:
    """
    Get a colored logger for a specific market

    Args:
        market_id: The market identifier
        strategy_index: Optional index for the strategy (for naming)

    Returns:
        Configured logger with colored output
    """
    return _market_logger_manager.get_market_logger(market_id, strategy_index)


def get_market_name(market_id: str) -> str:
    """Get the display name for a market"""
    return _market_logger_manager.get_market_name(market_id)


def setup_root_logger(level: str = "WARNING", format_string: Optional[str] = None):
    """Setup the root logger with basic configuration"""
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        handlers=[]  # We'll add handlers per market
    )
