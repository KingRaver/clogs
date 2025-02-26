# 🔍 Clogs Project

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Anthropic Claude](https://img.shields.io/badge/AI-Claude-blueviolet)](https://www.anthropic.com/)
[![CoinGecko](https://img.shields.io/badge/API-CoinGecko-yellow)](https://www.coingecko.com/en/api)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

An advanced cryptocurrency analysis and trading insights platform that leverages AI to generate market intelligence for crypto assets including KAITO and major Layer 1 blockchains.

## 🌟 Project Overview

Clogs combines real-time market data from CoinGecko, AI analysis through Anthropic's Claude, and web automation to deliver comprehensive crypto market intelligence. The system tracks market movements, analyzes correlations between assets, detects smart money flows, and provides actionable insights via automated social media posts.

## ✨ Key Features

- **Real-time Market Analysis**: Continuous monitoring of price, volume, and market dynamics
- **Smart Money Detection**: Identification of institutional money movements and accumulation patterns
- **Cross-chain Intelligence**: Comparisons between KAITO and major Layer 1 blockchains (ETH, SOL, AVAX, DOT)
- **AI-Powered Insights**: Claude AI for natural language market analysis and sentiment evaluation
- **Volume Trend Analysis**: Sophisticated detection of significant volume movements
- **Automated Social Media**: Twitter integration for posting timely market insights
- **Historical Data Storage**: SQLite database for trend analysis and pattern recognition
- **Adaptive Content**: Smart duplicate detection with configurable sensitivity
- **Google Sheets Integration**: Data visualization and export capabilities

## 🧩 System Architecture

```
clogs/
│
├── README.md                   # Project documentation
├── __init__.py                 # Package initialization
├── architecture.txt            # Technical architecture overview
│
├── data/                       # Data storage
│   └── crypto_history.db       # SQLite database for historical data
│
├── logs/                       # Logging directory
│   ├── analysis/               # Detailed analysis logs
│   ├── api/                    # API interaction logs
│   └── system/                 # System operation logs
│
├── requirements.txt            # Project dependencies
│
└── src/                        # Source code
    ├── bot.py                  # Main bot implementation
    ├── coingecko_handler.py    # CoinGecko API integration
    ├── config.py               # System configuration
    ├── meme_phrases.py         # Crypto-specific meme content
    ├── mood_config.py          # Market sentiment definitions
    │
    └── utils/                  # Utility modules
        ├── browser.py          # Selenium automation tools
        ├── logger.py           # Logging system
        └── sheets_handler.py   # Google Sheets integration
```

## 🔧 Technical Requirements

- **Python**: 3.11 or higher
- **Dependencies**: 
  - Selenium 4.16.0+
  - Anthropic Python SDK
  - NumPy
  - Requests
  - SQLite3
- **API Access**:
  - Anthropic Claude API key
  - CoinGecko API access
  - (Optional) Google Sheets API credentials
- **System**:
  - Chrome/Chromium browser
  - ChromeDriver compatible with browser version

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/clogs.git
   cd clogs
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   Create a `.env` file in the project root:
   ```
   CLAUDE_API_KEY=your_anthropic_api_key
   COINGECKO_API_KEY=your_coingecko_api_key
   COINGECKO_BASE_URL=https://api.coingecko.com/api/v3
   TWITTER_USERNAME=your_twitter_username
   TWITTER_PASSWORD=your_twitter_password
   CHROME_DRIVER_PATH=/path/to/chromedriver
   ```

4. **Initialize the database**
   ```bash
   python src/database.py --init
   ```

## 🎮 Usage

### Running the Main Bot

```bash
python src/bot.py
```

### Configuration Options

Edit `config.py` to adjust:
- Monitoring frequency
- Price change thresholds
- Volume analysis sensitivity
- Smart money detection parameters
- Duplicate content detection settings

## 🔍 Core Analysis Features

### Market Data Collection
- Real-time price and volume tracking
- Historical data storage and retrieval
- Cross-chain comparison metrics

### Volume Analysis
- Z-score based anomaly detection
- Trend classification (significant/moderate increase/decrease)
- Hour-by-hour volume distribution analysis

### Smart Money Detection
- Price-volume divergence identification
- Stealth accumulation patterns
- Unusual trading hour detection
- Volume clustering analysis

### Layer 1 Comparisons
- Performance differential analysis
- Correlation measurements
- Relative strength indicators

### AI-Driven Insights
- Natural language market analysis
- Sentiment classification
- Context-aware content generation
- Meme-infused crypto commentary

## 🔄 Workflow

1. **Data Collection**: Regular polling of CoinGecko API for market data
2. **Analysis Triggering**: Detection of significant market events
3. **Intelligence Generation**: AI analysis of market conditions
4. **Content Distribution**: Automated Twitter posting
5. **Data Storage**: Archival of market data and analysis results

## 🛠️ Troubleshooting

### Common Issues

- **Duplicate Content Detection**: If analysis posts are being blocked as duplicates, check the settings in the `_is_duplicate_analysis` method in `bot.py`. The similarity threshold and timeframe can be adjusted.

- **Selenium Errors**: If you encounter "stale element" errors, these typically indicate Twitter's interface changed during element access. The bot is designed to continue functioning despite these errors.

- **API Rate Limiting**: CoinGecko and Claude API have rate limits. Adjust polling intervals in `config.py` if you encounter rate limit errors.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b new-feature`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin new-feature`
5. Submit a pull request

## 📄 License

[MIT](https://opensource.org/licenses/MIT)

## 📱 Contact

[https://linktr.ee/vvai](https://linktr.ee/vvai)

---

*Disclaimer: This software is for informational purposes only. Not financial advice.*
