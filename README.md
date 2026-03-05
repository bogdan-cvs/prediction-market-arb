# Prediction Market Arbitrage Tool

Cross-platform arbitrage detection and execution between **Kalshi**, **Polymarket**, **Limitless Exchange**, and **ForecastEx (IBKR)**.

## Features

- **Multi-platform connectors** — Real-time market data from 4 prediction markets
- **Fuzzy matching** — Automatically matches equivalent markets across platforms (entity extraction + rapidfuzz)
- **Arbitrage scanner** — Detects profitable YES/NO pairs where total cost < $1.00
- **Fee-aware profitability** — Net profit calculation after platform-specific fees and slippage
- **Simultaneous execution** — Both legs execute concurrently via asyncio
- **Risk management** — Per-market limits, total exposure cap, daily loss limit, kill switch
- **Dry run mode** — Default ON. Simulates trades before going live
- **Real-time UI** — React dashboard with WebSocket updates, trade history, P&L tracking

## Architecture

```
Backend (Python/FastAPI)     Frontend (React/Vite/Tailwind)
┌─────────────────────┐     ┌──────────────────────┐
│ Connectors           │     │ Dashboard             │
│  ├─ Kalshi           │     │  ├─ Opportunities     │
│  ├─ Polymarket       │◄───►│  ├─ Execution Panel   │
│  ├─ Limitless        │ WS  │  ├─ Portfolio View    │
│  └─ IBKR/ForecastEx  │     │  ├─ Market Matcher    │
│                      │     │  ├─ Profit Tracker    │
│ Matching Engine      │     │  └─ Settings          │
│ Arbitrage Scanner    │     └──────────────────────┘
│ Execution Engine     │
│ Risk Manager         │
└─────────────────────┘
```

## Quick Start (Windows)

### Prerequisites

- Python 3.11+
- Node.js 18+
- (Optional) IBKR TWS or IB Gateway for ForecastEx

### Setup

1. **Clone and enter project:**
   ```bash
   cd prediction-market-arb
   ```

2. **Backend setup:**
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Frontend setup:**
   ```bash
   cd frontend
   npm install
   ```

4. **Configure API keys:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Run:**
   ```bash
   # Option A: Use the launcher
   start.bat

   # Option B: Manual
   # Terminal 1:
   cd backend && python -m uvicorn main:app --reload --port 8000
   # Terminal 2:
   cd frontend && npm run dev
   ```

6. **Open:** http://localhost:5173

## API Keys Setup

### Kalshi
- Create account at [kalshi.com](https://kalshi.com)
- Generate API key + RSA private key in account settings
- Save private key to `keys/kalshi_private.pem`

### Polymarket
- Need an Ethereum wallet (private key) for CLOB trading
- Deposit USDC on Polygon network
- Set `POLYMARKET_PRIVATE_KEY` in `.env`

### Limitless Exchange
- Ethereum wallet on Base network
- Deposit USDC on Base
- Set `LIMITLESS_PRIVATE_KEY` in `.env`

### ForecastEx (IBKR)
- Interactive Brokers account with ForecastEx access
- Run TWS or IB Gateway on port 7497 (paper) or 7496 (live)
- No separate API key needed — connects via TWS API

## Configuration

All settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `true` | Simulate trades (no real orders) |
| `MIN_PROFIT_CENTS` | `2` | Minimum net profit per contract to flag |
| `MIN_QUANTITY` | `10` | Minimum available quantity |
| `SCAN_INTERVAL_SECONDS` | `3` | Seconds between scan cycles |
| `MAX_EXPOSURE_PER_MARKET` | `100` | Max $ exposure per matched market |
| `MAX_TOTAL_EXPOSURE` | `1000` | Max $ total exposure across all markets |
| `MAX_DAILY_LOSS` | `50` | Max $ daily realized loss before stopping |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service status + platform connections |
| `GET` | `/api/markets` | List markets (optionally filter by platform) |
| `GET` | `/api/markets/matches` | Cross-platform matched markets |
| `POST` | `/api/markets/matches/refresh` | Re-scan and match markets |
| `GET` | `/api/arb/opportunities` | Current arbitrage opportunities |
| `POST` | `/api/arb/scan` | Trigger manual scan |
| `POST` | `/api/execution/execute` | Execute an opportunity |
| `GET` | `/api/execution/history` | Trade history |
| `GET` | `/api/portfolio/summary` | Portfolio balances + P&L |
| `WS` | `/ws` | Real-time WebSocket updates |

Interactive docs: http://localhost:8000/docs

## How Arbitrage Works

```
Platform A: BTC > $100K by Mar 14?  YES = $0.42
Platform B: BTC > $100K by Mar 14?   NO = $0.55
                                    ─────────
Total cost:                          $0.97

Guaranteed payout:                   $1.00
Gross profit:                        $0.03 per contract

After fees (~$0.01):                 $0.02 net profit
At 100 contracts:                    $2.00 risk-free profit
```

## Important Notes

- **DRY RUN is ON by default.** Toggle in the UI or set `DRY_RUN=false` in `.env`
- **ForecastEx does not support SELL.** To exit, buy the opposite outcome (YES→NO or NO→YES)
- Each connector works independently — you can run with just Kalshi + Polymarket
- IBKR connector degrades gracefully if TWS is not running (uses mock data)
- All prices stored internally as integers (cents) to avoid float precision issues

## Disclaimer

This tool is for educational and research purposes. Trading on prediction markets involves risk. Ensure you comply with all applicable laws and platform terms of service in your jurisdiction.
