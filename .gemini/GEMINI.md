# TradingAgents Dashboard — AI Context

> Instructions and context for AI assistants working on this project.
> Load `project.md` first for full architecture reference.

---

## Project Identity

- **Project:** TradingAgents Dashboard
- **Owner:** Brian Galvan
- **Domain:** tradingagents.website
- **Purpose:** Personal AI-powered stock research platform. NOT a commercial product.
- **Repo:** bgalvan1277/tradingagents-dashboard (private)

---

## Critical Rules

1. **No frameworks.** Static HTML5, Vanilla CSS3, Vanilla JS. No React, no Tailwind, no Next.js.
2. **No AI giveaway phrases.** Avoid "delve", "landscape", "leverage", "in today's world", "game-changer".
3. **No EM dashes.** Use commas, periods, or semicolons instead.
4. **Hosting is cPanel VPS.** Server IP `162.248.48.164`. SSH as root. NOT AWS, NOT Vercel, NOT Heroku.
5. **FTP deploy does NOT restart Python.** Template changes (HTML/CSS/JS) auto-reload. Python code changes (routes, services, models) require `systemctl restart tradingagents`. **Always warn the user when a Python change needs a restart.**
5. **Single-password auth.** No user accounts. One password for dashboard access.
6. **DeepSeek is the LLM.** Not OpenAI, not Anthropic. Uses OpenAI-compatible API format via LangChain.
7. **All public pages use 1100px max-width.** Consistency across home, how-it-works, about, contact, faq.
8. **Dark mode only.** The entire site is dark-themed. No light mode.
9. **Cost caps are real.** $10/day, $100/month. Always respect cost_log enforcement.
10. **Agent names are fixed.** Do not rename, remove, or add agents without explicit instruction.

---

## Tech Stack Quick Reference

| What | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| DB | MySQL (aiomysql async) |
| ORM | SQLAlchemy 2.0 async |
| Templates | Jinja2 |
| CSS | Vanilla (no Tailwind) |
| JS | Vanilla (no React) |
| LLM | DeepSeek v4 (via langchain) |
| Deploy | GitHub Actions -> FTP -> cPanel |

---

## File Loading Order

When working on this project, load context in this order:
1. Global user rules (no frameworks, no AI phrases, etc.)
2. This file (`.gemini/GEMINI.md`) for project-specific AI rules
3. `project.md` at repo root for full architecture reference

---

## Architecture Notes

### Two Template Systems
The site has TWO separate base templates:
- **`app/templates/public/base.html`** — Public marketing pages (nav with Home, How It Works, About, Contact, FAQ + login CTA)
- **`app/templates/base.html`** — Authenticated dashboard pages (sidebar navigation)

Public pages extend `public/base.html`. Dashboard pages extend `base.html`. Never mix them.

### Route Organization
- **`app/routes/public.py`** — All unauthenticated public page routes
- **Other route files** — All require authentication via `require_auth(request)`

### OSINT Layer (Colonel Wolfe)
The file `app/services/colonel_wolfe.py` is the most critical service file. It contains:
- SEC EDGAR query functions
- USASpending.gov federal contract lookups
- FRED macroeconomic indicator fetches
- Reddit sentiment via ApeWisdom
- Comprehensive yfinance data (fundamentals, technicals, earnings, sector rotation, options, insiders)
- The briefing compiler that formats all data into an intelligence document

This runs as **Phase 0** before the TradingAgents framework executes Phases 1-4.

### Cost Metering
- `run_analysis_sync()` wraps `ta.propagate()` with LangChain's `get_openai_callback()`
- Captures input/output tokens per run
- Writes to `cost_log` table via `save_run_results()`
- Status page reads from `cost_log` to display spend
- DeepSeek pricing is hardcoded in `runner.py` (`_DEEPSEEK_PRICING` dict)

### SimTrader
- Paper trading module with $100,000 starting balance
- Tables: `sim_account`, `sim_trades`, `sim_positions`
- Supports market-price and custom-price entries
- Service logic in `app/services/simtrader.py`

---

## Design Tokens

```css
/* Colors */
--bg-base: #0a0e17;
--bg-surface: #0f172a;
--accent-cyan: #22d3ee;  /* rgba(6,182,212,...) */
--accent-blue: #3b82f6;  /* rgba(59,130,246,...) */
--text-heading: #f1f5f9;
--text-body: #94a3b8;
--text-muted: #64748b;
--border: rgba(71,85,105,.25);

/* Spacing */
--card-radius: 16px-24px;
--input-radius: 10px;
--page-max-width: 1100px;
--page-padding: 0 2rem;

/* Effects */
backdrop-filter: blur(16px);  /* glassmorphism on cards */
```

---

## Agent Roster (DO NOT CHANGE)

| Name | Role | Stage |
|---|---|---|
| Col. Don Wolfe (RET) | Intelligence Officer (OSINT) | 0 |
| Marcus Chen | Chief Technical Analyst | 1 |
| Sarah Mitchell | Sentiment Intelligence Lead | 1 |
| James Rivera | News and Media Analyst | 1 |
| Elena Kowalski | Fundamentals Research Lead | 1 |
| David Park | Bull Case Advocate | 2 |
| Catherine Walsh | Bear Case Advocate | 2 |
| Michael Torres | Research Director (Judge) | 3 |
| Risk Committee | 3-perspective risk panel | 4 |
| Brian Galvan | Portfolio Manager (human) | 5 |

---

## Current Watchlist Tickers

| Symbol | Company |
|---|---|
| BE | Bloom Energy |
| CRWV | CoreWeave |
| MU | Micron Technology |
| NVDA | NVIDIA Corporation |
| PLTR | Palantir Technologies |
| SOUN | SoundHound AI |

---

## Common Tasks

### Add a new public page
1. Create template in `app/templates/public/` extending `public/base.html`
2. Set `{% set active_page = 'name' %}`
3. Add route in `app/routes/public.py`
4. Add nav link in `app/templates/public/base.html` (both desktop and mobile nav)
5. Use `max-width:1100px` for consistency

### Fix a ticker name
Visit (while logged in): `https://tradingagents.website/api/ticker/SYMBOL/rename?name=CorrectName`

### Cancel a stuck run
Click the X button on the run queue page, or POST to `/run/{run_id}/cancel`

### Run analysis manually
On the server: `python scripts/run_single.py TICKER [YYYY-MM-DD]`

---

## Known Behaviors

- Analysis runs take 3-8 minutes per ticker depending on model and debate complexity
- The LangChain `get_openai_callback` may not capture all token usage from DeepSeek; cost is estimated from published pricing as fallback
- Colonel Wolfe's SEC EDGAR queries use the EFTS search index which occasionally returns 404s
- Reddit sentiment via ApeWisdom only covers top ~100 mentioned tickers
- SimTrader uses live yfinance prices at time of trade execution
