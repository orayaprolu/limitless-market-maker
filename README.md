# Limitless Market Maker
### Production-Scale Automated Trading System | Python • Web3 • Real-Time Data Processing

A sophisticated **algorithmic trading platform** built for Limitless Exchange that demonstrates advanced software engineering principles through automated market making and reward farming strategies. This system showcases expertise in **distributed systems**, **real-time data processing**, **blockchain integration**, and **financial technology**.

## 🎥 Live Demo

[Demo Video](https://youtu.be/ANddlAX7ZrI)

---

## Technical Highlights

**What This Project Demonstrates:**
- **Concurrent Programming**: Multi-threaded strategy execution with real-time data processing
- **API Design**: RESTful client architecture with rate limiting and error handling
- **Financial Engineering**: Options pricing models integrated with prediction market mechanics
- **Blockchain Development**: Direct Web3 integration for decentralized trading
- **System Architecture**: Modular, scalable design supporting multiple trading strategies
- **Production Monitoring**: Comprehensive logging, error handling, and performance tracking

---

## System Architecture

**Key Components:**
- **Strategy Manager**: Orchestrates multiple concurrent trading strategies
- **Data Streams**: Real-time feeds from Limitless Exchange + Deribit options data
- **Risk Engine**: Position limits, spread controls, and automated safety mechanisms
- **Blockchain Proxy**: Direct Web3 interaction with gas optimization
- **Monitoring Stack**: Structured logging with market-specific performance tracking

---

## Tech Stack

**Backend & Core:**
- **Python 3.8+** - Core application logic
- **asyncio/threading** - Concurrent execution
- **Web3.py** - Blockchain integration
- **requests/aiohttp** - HTTP client libraries

**Data & Analytics:**
- **NumPy/SciPy** - Mathematical operations for pricing models
- **Pandas** - Market data analysis
- **Real-time WebSockets** - Live data streaming

**Infrastructure:**
- **Docker** - Containerized deployment
- **Structured Logging** - Production monitoring
- **Environment Config** - Secure credential management
- **Base Network** - Ethereum L2 for low-cost transactions

---

## Key Features

### Advanced Trading Logic
- **Multi-Market Orchestration**: Parallel execution across multiple prediction markets
- **Options-Based Pricing**: Integrates Deribit derivatives data for fair value calculation
- **Dynamic Spread Management**: Algorithmic bid-ask optimization based on market conditions
- **Reward Optimization**: Designed specifically for Limitless Exchange incentive programs

### Production-Ready Engineering
- **Fault Tolerance**: Comprehensive error handling with automatic recovery
- **Rate Limiting**: Built-in API throttling to prevent service disruption
- **Gas Optimization**: Smart contract interaction cost minimization
- **Hot Configuration**: Runtime strategy parameter updates without restart
- **Performance Monitoring**: Real-time P&L tracking and system metrics

### Security & Risk Management
- **Position Limits**: Automated exposure controls per market
- **Slippage Protection**: Maximum acceptable price deviation guards
- **Private Key Security**: Environment-based credential management
- **Transaction Validation**: Pre-flight checks for all blockchain operations

---

## Quick Start

```bash
# Clone and setup
git clone <repository-url>
cd limitless-market-maker
python -m venv venv && source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Add your PRIVATE_KEY and configuration

# Launch trading system
python main.py
```

**Environment Variables:**
```env
PRIVATE_KEY=your_ethereum_private_key    # Base network wallet
BASE_RPC=https://mainnet.base.org        # RPC endpoint (optional)
LOG_LEVEL=INFO                           # Logging verbosity
STRATEGY_LOG_LEVEL=DEBUG                 # Strategy-specific logs
```

---

## Strategy Implementation

The **RewardFarmer** strategy demonstrates sophisticated financial engineering:

```python
class RewardFarmer:
    def __init__(self, client, limitless_stream, deribit_stream, allocation, market_data):
        # Initialize with real-time data streams and risk parameters
        self._bba_limit_ratio = Decimal('1.5')      # Best bid/ask constraints
        self._order_limit_ratio = Decimal('3')      # Position sizing limits
        self._max_half_spread = client.get_max_half_spread()

    def trading_loop(self):
        # 1. Update market data from multiple sources
        # 2. Calculate fair values using options pricing
        # 3. Generate optimized bid/ask quotes
        # 4. Execute trades with gas optimization
        # 5. Monitor positions and adjust risk
```

**Core Algorithm:**
1. **Data Ingestion**: Parallel streams from Limitless + Deribit APIs
2. **Fair Value Calculation**: Options-derived pricing models
3. **Quote Generation**: Spread optimization based on market conditions
4. **Risk-Adjusted Execution**: Position-aware order sizing
5. **Performance Tracking**: Real-time P&L and metrics logging

---

## Performance & Monitoring

**Real-Time Dashboards:**
- Position tracking across all markets
- P&L attribution by strategy
- API latency and error rates
- Gas usage optimization metrics
- Trading volume and reward tracking

**Production Logging:**
```python
# Market-specific loggers with structured data
market_logger.info("Order executed", extra={
    "market_id": market_id,
    "side": "BUY",
    "size": order_size,
    "price": execution_price,
    "gas_used": tx_receipt.gasUsed
})
```

---

## Let's Connect

I'm passionate about **algorithmic trading**, **distributed systems**, and **blockchain technology**. Always interested in discussing complex engineering challenges and innovative financial technology.

**Professional Links:**
- 💼 **LinkedIn**: [linkedin.com/in/ojas](https://linkedin.com/in/ojas-rayaprolu)
- 🔗 **GitHub**: [github.com/ojaskrishna](https://github.com/orayaprolu)
- 🐦 **Twitter/X**: [twitter.com/ojastrades](https://x.com/orayaprolu)
