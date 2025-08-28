# Limitless Market Maker

A sophisticated automated market making system for Limitless Exchange that implements reward farming strategies on cryptocurrency prediction markets. This system provides liquidity while earning trading rewards through algorithmic market making.

## 🎥 Demo

<!-- Replace with your actual demo video -->
[![Demo Video](https://img.youtube.com/vi/YOUR_VIDEO_ID/0.jpg)](https://www.youtube.com/watch?v=YOUR_VIDEO_ID)

*Or upload your demo.mp4 file to the repository and link it here:*
[📹 Watch Demo](./demo.mp4)

## 🌟 Features

- **Automated Market Making**: Continuously provides liquidity on multiple prediction markets
- **Reward Farming Strategy**: Optimized for earning Limitless Exchange trading rewards
- **Multi-Market Support**: Simultaneous trading across multiple Bitcoin price prediction markets
- **Deribit Integration**: Uses Deribit options data for sophisticated pricing models
- **Real-time Data Streams**: Live market data from both Limitless Exchange and Deribit
- **Risk Management**: Built-in position limits and spread controls
- **Comprehensive Logging**: Detailed logging with market-specific loggers
- **Web3 Integration**: Direct blockchain interaction for trading operations

## 🏗️ Architecture

The system is built with a modular architecture:

```
├── main.py                 # Main application entry point
├── config/                 # Configuration files
│   └── strategy_config.py  # Strategy and market configurations
├── clients/                # Exchange clients
│   └── limitless_client.py # Limitless Exchange API client
├── datastreams/            # Real-time data feeds
│   ├── limitless_datastream.py  # Limitless market data
│   └── deribit_datastream.py    # Deribit options data
├── strategy/               # Trading strategies
│   └── reward_farmer.py    # Main reward farming strategy
├── proxies/                # Blockchain proxies
│   └── limitless_proxy.py  # Web3 trading proxy
├── models/                 # Data models
│   ├── marketdata.py       # Market data structures
│   ├── bba.py             # Best bid/ask models
│   └── constants.py       # Application constants
└── utils/                  # Utility functions
    ├── colored_logging.py  # Enhanced logging system
    └── snap.py            # Price snapping utilities
```

## 📋 Prerequisites

- Python 3.8+
- Base Network RPC access
- Ethereum private key with Base ETH for gas
- Limitless Exchange account

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd limitless-market-maker
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment setup**
   ```bash
   cp .env.example .env  # Create from template
   # Edit .env with your configuration
   ```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# Required: Your Ethereum private key (with Base ETH for gas)
PRIVATE_KEY=your_private_key_here

# Optional: Custom RPC endpoints
BASE_RPC=https://mainnet.base.org

# Optional: Logging configuration
LOG_LEVEL=INFO
STRATEGY_LOG_LEVEL=DEBUG
```

### Strategy Configuration

Edit `config/strategy_config.py` to configure your trading strategies:

```python
STRATEGY_CONFIGS = [
    StrategyConfig(
        market_id="your-market-id-here",
        deribit_config=DeribitConfig(
            lower_instrument_earlier='BTC-30AUG25-106000-C',
            upper_instrument_later='BTC-30AUG25-108000-C',
            # ... other instruments
        ),
        allocation=50  # USD allocation for this market
    ),
    # Add more strategy configurations
]
```

## 🔧 Usage

### Basic Usage

Run the market maker:

```bash
python main.py
```

### Advanced Options

The system automatically:
- Initializes all configured strategies
- Connects to data streams
- Begins automated trading loops
- Provides real-time position updates

### Monitoring

Monitor your strategies through:
- Console output with colored logging
- Log files in the `logs/` directory
- Position summaries printed periodically

## 📊 Strategy Details

### Reward Farmer Strategy

The core `RewardFarmer` strategy implements:

- **Dynamic Pricing**: Uses Deribit options data to calculate fair values
- **Spread Management**: Maintains profitable bid-ask spreads
- **Position Limits**: Controls maximum exposure per market
- **Liquidity Provision**: Continuously quotes both sides of the market

### Key Parameters

- `allocation`: USD amount allocated to each market
- `max_half_spread`: Maximum half-spread for orders
- `tick_size`: Minimum price increment
- `bba_limit_ratio`: Best bid/ask ratio limits
- `order_limit_ratio`: Order size ratio limits

## 🛡️ Risk Management

The system includes multiple risk management features:

- **Position Limits**: Maximum exposure per market
- **Spread Controls**: Minimum and maximum spread requirements
- **Gas Management**: Optimized gas usage for transactions
- **Error Handling**: Comprehensive error handling and recovery
- **Rate Limiting**: Respects exchange rate limits

## 📈 Performance Monitoring

### Logging Levels

- `INFO`: General system information
- `DEBUG`: Detailed strategy execution
- `WARNING`: Important alerts
- `ERROR`: System errors

### Position Tracking

The system provides:
- Real-time position updates
- P&L tracking per market
- Trade history logging
- Performance metrics

## 🔍 Troubleshooting

### Common Issues

1. **Insufficient Gas**
   - Ensure your wallet has Base ETH for transaction fees
   - Check gas price settings in constants.py

2. **API Rate Limits**
   - The system respects rate limits automatically
   - Reduce number of markets if issues persist

3. **Network Connectivity**
   - Check RPC endpoint connectivity
   - Verify internet connection stability

4. **Market Data Issues**
   - Ensure market IDs are correct and active
   - Check Deribit instrument names are valid

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
export STRATEGY_LOG_LEVEL=DEBUG
python main.py
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This software is for educational and research purposes only. Trading cryptocurrencies and prediction markets involves substantial risk of loss. Users should:

- Understand the risks involved in automated trading
- Start with small allocations
- Monitor positions regularly
- Ensure compliance with local regulations
- Use at their own risk

The authors are not responsible for any financial losses incurred through the use of this software.

## 🔗 Resources

- [Limitless Exchange](https://limitless.exchange)
- [Base Network](https://base.org)
- [Deribit API Documentation](https://docs.deribit.com)
- [Web3.py Documentation](https://web3py.readthedocs.io)

## 📞 Support

For support and questions:
- Open an issue on GitHub
- Join our community discussions
- Review the documentation and code comments

---

**Happy Trading! 🚀**