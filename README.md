# TradingAgents Dashboard

Personal web dashboard for the [TradingAgents](https://github.com/TauricResearch/TradingAgents) multi-agent stock analysis framework. Runs LLM-powered agents that analyze tickers from four perspectives (fundamentals, sentiment, news, technicals), hosts a bull/bear debate, then synthesizes a 5-tier rating (Buy / Overweight / Hold / Underweight / Sell).

This is a single-user research tool. No real money, no brokerage connections, no trading.

## Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy (async)
- **Database**: MySQL (via aiomysql)
- **Frontend**: Jinja2 templates, HTMX, Tailwind CSS v3 (CDN)
- **LLM Provider**: DeepSeek V4 (OpenAI-compatible API)
- **Market Data**: yfinance (default), Alpha Vantage (optional)
- **Auth**: Single password, session cookie

## Pages

| Route | Description |
|-------|-------------|
| `/` | Dashboard grid showing latest rating per ticker |
| `/ticker/{symbol}` | Full analysis with collapsible agent reports |
| `/history` | All runs with filtering (ticker, rating, date range) |
| `/watchlist` | Add, remove, categorize tickers |
| `/run` | Trigger on-demand analysis |
| `/status` | API spend, cron health, recent failures |
| `/login` | Password gate |

## Setup

### 1. Clone and install

```bash
git clone https://github.com/bgalvan1277/tradingagents-dashboard.git
cd tradingagents-dashboard
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -e .
pip install tradingagents
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your database credentials and DeepSeek API key
```

### 3. Database

Create a MySQL database and user, then run migrations:

```bash
mysql -u root -p -e "CREATE DATABASE tradingagents_db CHARACTER SET utf8mb4;"
mysql -u root -p -e "CREATE USER 'tradingagents_user'@'localhost' IDENTIFIED BY 'your_password';"
mysql -u root -p -e "GRANT ALL ON tradingagents_db.* TO 'tradingagents_user'@'localhost';"

alembic upgrade head
python scripts/seed_watchlist.py
```

### 4. Run locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Daily cron (weekdays at 7am)

```
0 7 * * 1-5 cd /path/to/project && /path/to/venv/bin/python scripts/daily_cron.py
```

## Cost Protection

- Daily cap: $10 (configurable via `DAILY_COST_CAP_USD`)
- Monthly cap: $100 (configurable via `MONTHLY_COST_CAP_USD`)
- Cost checked before each ticker run
- All token usage logged to `cost_log` table

## License

Private project. Not for redistribution.
