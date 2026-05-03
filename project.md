# TradingAgents Dashboard — Project Reference

> Comprehensive project reference for the TradingAgents autonomous AI research platform.
> This is the single source of truth for architecture, infrastructure, and design decisions.

---

## Overview

**TradingAgents** is a personal autonomous multi-agent stock research platform built by **Brian Galvan**. It deploys 9 AI agents across 6 analytical stages to produce institutional-grade stock analysis. It extends the open-source [TradingAgents framework](https://github.com/TauricResearch/TradingAgents) from Tauric Research with a proprietary OSINT intelligence layer, custom agent personas, and a full-stack analytical dashboard.

- **Domain:** `tradingagents.website`
- **Repo:** `bgalvan1277/tradingagents-dashboard`
- **Branch:** `main`
- **Purpose:** Personal portfolio research tool, NOT a commercial product

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.10+, FastAPI, Uvicorn |
| **Database** | MySQL (aiomysql async driver, pymysql for migrations) |
| **ORM** | SQLAlchemy 2.0 (async) |
| **Migrations** | Alembic |
| **Templates** | Jinja2 |
| **Frontend** | Static HTML5, Vanilla CSS3, Vanilla JS (no frameworks) |
| **LLM Provider** | DeepSeek (OpenAI-compatible API) |
| **AI Framework** | TradingAgents (Tauric Research, LangChain-based) |
| **Deployment** | cPanel via FTP (GitHub Actions auto-deploy on push to main) |
| **Auth** | Single password, cookie-based sessions (itsdangerous) |

---

## Hosting & Deployment

- **Hosting:** cPanel-based VPS (AlmaLinux 8)
- **Server IP:** `162.248.48.164`
- **SSH:** `ssh root@162.248.48.164`
- **Domain:** `tradingagents.website`
- **App path:** `/home/tradingagents/dashboard/`
- **Python:** 3.11, virtual env at `/home/tradingagents/dashboard/venv/`
- **Process manager:** systemd service named `tradingagents`
- **Web server:** Apache reverse proxy -> uvicorn on port 8000
- **Deploy method:** GitHub Actions -> FTP Deploy to cPanel on push to `main`
- **Deploy workflow:** `.github/workflows/deploy.yml`
- **FTP credentials:** Stored as GitHub Secrets (`FTP_SERVER`, `FTP_USERNAME`, `FTP_PASSWORD`)
- **Excluded from deploy:** `.git`, `venv/`, `__pycache__/`, `.env`, `logs/`

> **CRITICAL DEPLOYMENT RULE:**
> FTP deploy only copies files. It does NOT restart the Python process.
> - **HTML/CSS/JS template changes** take effect immediately (Jinja2 reads from disk)
> - **Python code changes** (routes, services, models) require a server restart:
>   ```bash
>   ssh root@162.248.48.164
>   cd /home/tradingagents/dashboard && git pull && systemctl restart tradingagents
>   ```
> - Always warn the user when a Python code change needs a restart.

---

## Server Commands Quick Reference

| Task | Command |
|---|---|
| SSH in | `ssh root@162.248.48.164` |
| Pull latest code | `cd /home/tradingagents/dashboard && git pull` |
| Restart app | `systemctl restart tradingagents` |
| Check status | `systemctl status tradingagents` |
| View live logs | `journalctl -u tradingagents -f` |
| Restart Apache | `/scripts/restartsrv_httpd` |
| Run single analysis | `cd /home/tradingagents/dashboard && source venv/bin/activate && python scripts/run_single.py TICKER` |
| Daily cron | `0 7 * * 1-5` (weekdays 7am, runs as tradingagents user) |

---

## Directory Structure

```
Trading Agents/
├── .github/workflows/deploy.yml    # Auto-deploy on push
├── app/
│   ├── main.py                     # FastAPI app entry point
│   ├── config.py                   # Pydantic settings from .env
│   ├── models.py                   # SQLAlchemy models (Run, RunDetail, Ticker, CostLog, etc.)
│   ├── database.py                 # Async engine + session factory
│   ├── auth.py                     # Cookie-based single-password auth
│   ├── routes/
│   │   ├── public.py               # Public pages (home, how-it-works, about, contact, faq)
│   │   ├── login.py                # Auth login/logout
│   │   ├── dashboard.py            # Main dashboard (post-login)
│   │   ├── portfolio.py            # Portfolio overview
│   │   ├── ticker.py               # Individual ticker detail view
│   │   ├── watchlist.py            # Watchlist CRUD + ticker rename API
│   │   ├── run.py                  # Run analysis (queue, submit, cancel)
│   │   ├── history.py              # Analysis history
│   │   ├── status.py               # System status (cost metering, cron logs)
│   │   ├── intelligence.py         # Intelligence hub (Col. Wolfe data)
│   │   ├── about.py                # About page (dashboard)
│   │   └── simtrader.py            # SimTrader paper trading
│   ├── services/
│   │   ├── colonel_wolfe.py        # OSINT intelligence sweep (SEC, FRED, Reddit, yfinance)
│   │   ├── runner.py               # TradingAgents wrapper + cost metering
│   │   ├── cost.py                 # Cost tracking and cap enforcement
│   │   ├── intel_data.py           # Intelligence data helpers
│   │   └── simtrader.py            # SimTrader trade execution logic
│   ├── templates/
│   │   ├── public/                 # Public-facing pages (extends public/base.html)
│   │   │   ├── base.html           # Public layout (nav, footer)
│   │   │   ├── home.html           # Homepage with tabbed features showcase
│   │   │   ├── how.html            # How It Works pipeline walkthrough
│   │   │   ├── about.html          # About Us with agent roster
│   │   │   ├── contact.html        # Contact / project statement
│   │   │   └── faq.html            # FAQ (7 general + 10 agent deep dives)
│   │   ├── base.html               # Dashboard layout (sidebar nav)
│   │   ├── dashboard.html          # Main dashboard
│   │   ├── run.html                # Run analysis page
│   │   ├── simtrader.html          # SimTrader paper trading
│   │   └── ...                     # Other dashboard templates
│   └── static/                     # CSS, JS, images, avatars
├── scripts/
│   ├── run_single.py               # Run analysis for one ticker
│   ├── daily_cron.py               # Batch daily analysis for all active tickers
│   ├── seed_watchlist.py           # Initial watchlist seeding
│   └── fix_crwv.py                 # One-off ticker name fix
├── alembic/                        # Database migrations
├── pyproject.toml                  # Python project config
└── .env                            # Environment variables (not in git)
```

---

## Database Schema (Key Tables)

| Table | Purpose |
|---|---|
| `tickers` | Tracked stock symbols with names, categories, model tier |
| `watchlist_entries` | Grouping/ordering of tickers in watchlist |
| `runs` | Each analysis run (status, recommendation, cost, timestamp) |
| `run_details` | Full agent outputs per run (all 14 deliverables) |
| `cost_log` | Token usage and USD cost per LLM call |
| `cron_log` | Daily cron execution logs |
| `sim_account` | SimTrader cash balance (starts at $100,000) |
| `sim_trades` | Paper trade execution history |
| `sim_positions` | Current simulated holdings |

---

## Agent Pipeline (6 Stages)

| Stage | Agent(s) | Role |
|---|---|---|
| **0** | Col. Don Wolfe | OSINT Intelligence Sweep |
| **1** | Marcus Chen, Sarah Mitchell, James Rivera, Elena Kowalski | Research Analysts (Technical, Sentiment, News, Fundamentals) |
| **2** | David Park, Catherine Walsh | Adversarial Debate (Bull vs Bear) |
| **3** | Michael Torres | Research Director / Judicial Verdict |
| **4** | Risk Committee (3 perspectives + Risk Judge) | Risk Assessment |
| **5** | Brian Galvan (human) | Final Portfolio Decision |

---

## OSINT Data Sources (Colonel Wolfe)

| Source | API | Data |
|---|---|---|
| SEC EDGAR | `efts.sec.gov` | Form 4, 8-K, 13-F filings |
| USASpending.gov | `api.usaspending.gov` | Federal contracts |
| FRED | `fred.stlouisfed.org` | Fed rate, CPI, unemployment, Treasury yields, VIX |
| ApeWisdom | `apewisdom.io` | Reddit retail sentiment |
| yfinance | Python package | Fundamentals, technicals, earnings, sector rotation, options, insiders |

---

## LLM Configuration

- **Provider:** DeepSeek (via OpenAI-compatible API)
- **Deep Think Model:** `deepseek-v4-pro` ($0.14/M input, $0.28/M output)
- **Quick Think Model:** `deepseek-v4-flash` ($0.07/M input, $0.14/M output)
- **Base URL:** `https://api.deepseek.com`
- **Cost Caps:** $10/day, $100/month
- **Cost Metering:** LangChain `get_openai_callback` captures tokens per run, writes to `cost_log` table

---

## Key Environment Variables

See `.env.example` for full list. Critical ones:

- `DASHBOARD_PASSWORD` - single auth password
- `SECRET_KEY` - session signing key
- `DATABASE_URL` - MySQL async connection string
- `OPENAI_API_KEY` - DeepSeek API key (uses OpenAI client)
- `DEEP_THINK_MODEL` / `QUICK_THINK_MODEL` - model names
- `DAILY_COST_CAP_USD` / `MONTHLY_COST_CAP_USD` - cost protection

---

## Public Pages (all 1100px max-width)

| Route | Template | Description |
|---|---|---|
| `/` | `public/home.html` | Homepage with hero, tabbed features showcase, stats |
| `/how-it-works` | `public/how.html` | Pipeline walkthrough |
| `/about-us` | `public/about.html` | Agent roster + creator bio |
| `/contact` | `public/contact.html` | Project statement + LinkedIn/website links |
| `/faq` | `public/faq.html` | 7 general + 10 agent FAQs |

---

## Dashboard Pages (auth required)

| Route | Template | Description |
|---|---|---|
| `/login` | `login.html` | Password login |
| `/dashboard` | `dashboard.html` | Main overview |
| `/portfolio` | `portfolio.html` | Portfolio summary |
| `/ticker/{symbol}` | `ticker_detail.html` | Individual ticker analysis |
| `/watchlist` | `watchlist.html` | Manage tracked tickers |
| `/run` | `run.html` | Queue and trigger analysis |
| `/status` | `status.html` | System status, cost metering, cron logs |
| `/intelligence` | `intelligence/hub.html` | Intelligence hub |
| `/simtrader` | `simtrader.html` | Paper trading module |
| `/history` | `history.html` | Analysis run history |

---

## Current Watchlist

| Symbol | Company | Category |
|---|---|---|
| BE | Bloom Energy | — |
| CRWV | CoreWeave | — |
| MU | Micron Technology | — |
| NVDA | NVIDIA Corporation | — |
| PLTR | Palantir Technologies | — |
| SOUN | SoundHound AI | — |

---

## Design System

- **Aesthetic:** Dark mode, clean, data-dense, muted palette
- **Primary accent:** Cyan (`#22d3ee`, `rgba(6,182,212,...)`)
- **Secondary accent:** Blue (`#3b82f6`, `rgba(59,130,246,...)`)
- **Background:** `#0a0e17` base, `#0f172a` surfaces
- **Text:** `#f1f5f9` headings, `#94a3b8` body, `#64748b` muted
- **Border:** `rgba(71,85,105,.25)` standard, accent on hover
- **Radius:** 16-24px cards, 10px inputs/buttons
- **Glassmorphism:** `backdrop-filter:blur(16px)` on cards
- **Public page width:** All capped at `max-width:1100px`
- **No CSS frameworks** - all vanilla CSS

---

## Useful API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/ticker/{symbol}/rename?name=X` | GET | Rename a ticker (auth required) |
| `/api/run/{symbol}` | POST | Trigger analysis run |
| `/api/run/{run_id}/cancel` | POST | Cancel stuck run |
| `/run/{run_id}/cancel` | POST | Cancel and redirect |

---

## Scripts

| Script | Usage |
|---|---|
| `python scripts/run_single.py PLTR` | Run analysis for one ticker |
| `python scripts/daily_cron.py` | Batch run all active tickers |
| `python scripts/seed_watchlist.py` | Seed initial watchlist |
