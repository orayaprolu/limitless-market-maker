# Limitless Market Maker

A market making bot that uses prices binary options using options prices from deribit which is a much more liquid venue with very close to fair value

## 🎥 Live Demo

[Demo Video](https://youtu.be/ANddlAX7ZrI)

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
- **Base Network** - Ethereum L2 for low-cost transactions

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

**Professional Links:**
- 💼 **LinkedIn**: [linkedin.com/in/ojas-rayaprolu](https://linkedin.com/in/ojas-rayaprolu)
- 🔗 **GitHub**: [github.com/orayaprolu](https://github.com/orayaprolu)
- 🐦 **Twitter/X**: [twitter.com/orayaprolu](https://x.com/orayaprolu)
