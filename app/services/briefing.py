"""Day Trade Briefing service.

Runs a fast Col. Wolfe intelligence sweep on a ticker, then feeds the data
into a single DeepSeek LLM call that outputs a structured day-trade plan
with specific entry/exit prices, stop losses, targets, and strategy.

Also provides a quick screener that scores tickers by day-trade potential
using technical data only (no LLM cost for scanning).
"""

import json
import logging
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ── SCREENER: Score tickers by day-trade opportunity ──────────────────────────

def _score_ticker_sync(symbol: str) -> dict:
    """Score a single ticker for day-trade potential (sync, runs in executor).

    Returns a dict with score (0-100), price, key metrics, and signal flags.
    No LLM call, just pure technical/data scoring.
    """
    try:
        import yfinance as yf
        import numpy as np

        tk = yf.Ticker(symbol)
        info = tk.info or {}

        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        if not price or price <= 0:
            return {"symbol": symbol, "score": 0, "error": "No price data"}

        # Fetch 3-month history for technicals
        hist = tk.history(period="3mo")
        if hist is None or len(hist) < 20:
            return {"symbol": symbol, "score": 0, "error": "Insufficient history"}

        closes = hist["Close"].values
        volumes = hist["Volume"].values
        highs = hist["High"].values
        lows = hist["Low"].values

        score = 50  # Base score
        signals = []

        # ── Volume spike (big factor for day trading) ──
        avg_vol_20 = np.mean(volumes[-20:])
        current_vol = volumes[-1]
        vol_ratio = (current_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0
        if vol_ratio > 2.0:
            score += 15
            signals.append(f"Volume {vol_ratio:.1f}x avg — heavy activity")
        elif vol_ratio > 1.5:
            score += 10
            signals.append(f"Volume {vol_ratio:.1f}x avg — elevated")
        elif vol_ratio > 1.2:
            score += 5
            signals.append(f"Volume {vol_ratio:.1f}x avg — above normal")
        elif vol_ratio < 0.5:
            score -= 10
            signals.append("Volume dried up — avoid")

        # ── RSI extremes (mean reversion opportunities) ──
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-14:])
        avg_loss = np.mean(losses[-14:])
        rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100

        if rsi > 75:
            score += 8
            signals.append(f"RSI {rsi:.0f} — overbought, reversal potential")
        elif rsi < 25:
            score += 12
            signals.append(f"RSI {rsi:.0f} — oversold, bounce potential")
        elif 40 <= rsi <= 60:
            score += 3
            signals.append(f"RSI {rsi:.0f} — neutral, needs catalyst")

        # ── Average True Range (volatility = profit potential) ──
        tr_list = []
        for i in range(1, min(15, len(closes))):
            tr = max(
                highs[-i] - lows[-i],
                abs(highs[-i] - closes[-(i+1)]),
                abs(lows[-i] - closes[-(i+1)])
            )
            tr_list.append(tr)
        atr = np.mean(tr_list) if tr_list else 0
        atr_pct = (atr / price * 100) if price > 0 else 0

        if atr_pct > 5:
            score += 15
            signals.append(f"ATR {atr_pct:.1f}% — very high volatility")
        elif atr_pct > 3:
            score += 10
            signals.append(f"ATR {atr_pct:.1f}% — good day-trade range")
        elif atr_pct > 2:
            score += 5
            signals.append(f"ATR {atr_pct:.1f}% — moderate range")
        elif atr_pct < 1:
            score -= 10
            signals.append(f"ATR {atr_pct:.1f}% — too tight for day trading")

        # ── Price momentum (last 5 days) ──
        if len(closes) >= 6:
            five_day_move = (closes[-1] / closes[-6] - 1) * 100
            if abs(five_day_move) > 10:
                score += 10
                signals.append(f"5-day move {five_day_move:+.1f}% — momentum trade")
            elif abs(five_day_move) > 5:
                score += 5
                signals.append(f"5-day move {five_day_move:+.1f}% — trending")

        # ── Gap detection (today's open vs yesterday's close) ──
        if len(hist) >= 2:
            prev_close = closes[-2]
            today_open = hist["Open"].values[-1]
            gap_pct = (today_open / prev_close - 1) * 100
            if abs(gap_pct) > 3:
                score += 10
                signals.append(f"Gap {gap_pct:+.1f}% — gap trade setup")
            elif abs(gap_pct) > 1.5:
                score += 5
                signals.append(f"Gap {gap_pct:+.1f}% — minor gap")

        # ── Proximity to SMA-20 (bounce/rejection zone) ──
        sma_20 = np.mean(closes[-20:])
        dist_from_sma = (price - sma_20) / sma_20 * 100
        if abs(dist_from_sma) < 1:
            score += 5
            signals.append("Price at SMA-20 — key decision zone")

        # ── Short interest (squeeze potential) ──
        short_pct = info.get("shortPercentOfFloat")
        if short_pct and short_pct > 0.15:
            score += 10
            signals.append(f"Short {short_pct*100:.0f}% of float — squeeze candidate")
        elif short_pct and short_pct > 0.10:
            score += 5
            signals.append(f"Short {short_pct*100:.0f}% of float — elevated")

        # ── Float size (low float = explosive moves) ──
        float_shares = info.get("floatShares", 0)
        shares_outstanding = info.get("sharesOutstanding", 0)
        float_val = float_shares or shares_outstanding
        if float_val and float_val < 20e6:
            score += 8
            signals.append(f"Float {float_val/1e6:.1f}M — low float, explosive potential")
        elif float_val and float_val < 50e6:
            score += 4
            signals.append(f"Float {float_val/1e6:.1f}M — mid float")

        # ── Market cap filter (too large = low volatility) ──
        mcap = info.get("marketCap", 0)
        if mcap and mcap < 2e9:
            score += 5
            signals.append("Small-cap — higher volatility potential")
        elif mcap and mcap > 500e9:
            score -= 5
            signals.append("Mega-cap — lower intraday range")

        # ── Pre-market gap (check if market is open or pre-market) ──
        pre_price = info.get("preMarketPrice")
        prev_close_info = info.get("previousClose") or info.get("regularMarketPreviousClose")
        pre_gap_pct = None
        if pre_price and prev_close_info:
            pre_gap_pct = round((pre_price / prev_close_info - 1) * 100, 2)
            if abs(pre_gap_pct) > 3:
                score += 10
                signals.append(f"Pre-market gap {pre_gap_pct:+.1f}% — gapper alert")
            elif abs(pre_gap_pct) > 1.5:
                score += 5
                signals.append(f"Pre-market gap {pre_gap_pct:+.1f}%")

        # Clamp score
        score = max(0, min(100, score))

        # Determine bias direction
        sma_50 = np.mean(closes[-50:]) if len(closes) >= 50 else sma_20
        if price > sma_20 and price > sma_50:
            bias = "LONG"
        elif price < sma_20 and price < sma_50:
            bias = "SHORT"
        else:
            bias = "NEUTRAL"

        return {
            "symbol": symbol,
            "name": info.get("shortName") or info.get("longName") or symbol,
            "price": round(price, 2),
            "score": score,
            "bias": bias,
            "rsi": round(rsi, 1),
            "atr_pct": round(atr_pct, 1),
            "vol_ratio": round(vol_ratio, 1),
            "market_cap": mcap,
            "float_shares": float_val,
            "pre_gap_pct": pre_gap_pct,
            "signals": signals[:6],  # Top 6 signals
        }

    except Exception as e:
        logger.warning("Screener scoring failed for %s: %s", symbol, e)
        return {"symbol": symbol, "score": 0, "error": str(e)}


async def screen_tickers(symbols: list[str]) -> list[dict]:
    """Score multiple tickers for day-trade potential.

    Runs all tickers concurrently via thread pool.
    Returns list sorted by score (highest first).
    """
    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, _score_ticker_sync, s) for s in symbols]
    results = await asyncio.gather(*tasks)
    # Filter out errors and sort by score
    scored = [r for r in results if r.get("score", 0) > 0]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


# ── BRIEFING: Full trade plan via LLM ─────────────────────────────────────────

TRADE_PLAN_PROMPT = """You are an expert day trader and technical analyst. I'm giving you a comprehensive intelligence briefing on a stock ticker. Your job is to produce a structured day-trade plan.

IMPORTANT RULES:
- This is for INTRADAY trading only. Positions will be opened and closed within the same trading day.
- Give specific price levels, not vague ranges. Use the technical data provided.
- Be realistic about targets. A good day trade captures 1-5% moves, not moonshots.
- Always include a stop loss. Risk management is non-negotiable.
- If the setup is bad, say so. Don't force a trade. "No trade" is a valid recommendation.
- Consider the broader macro environment from the FRED data.
- Factor in options flow, insider activity, and sentiment when setting bias.
- Position sizing should assume a $100,000 account with max 10% risk per trade.

Return your analysis as valid JSON with this exact structure:
{{
    "direction": "LONG" or "SHORT" or "NO TRADE",
    "confidence": <integer 0-100>,
    "thesis": "<one sentence explaining why this trade>",
    "entry_low": <float>,
    "entry_high": <float>,
    "stop_loss": <float>,
    "stop_loss_pct": <float, negative percentage from entry midpoint>,
    "target_1": <float>,
    "target_1_pct": <float, percentage gain from entry midpoint>,
    "target_2": <float>,
    "target_2_pct": <float>,
    "target_3": <float>,
    "target_3_pct": <float>,
    "risk_reward": "<string like '1:2.3'>",
    "position_size_shares": <integer>,
    "position_size_dollars": <float>,
    "key_supports": [<float>, <float>, <float>],
    "key_resistances": [<float>, <float>, <float>],
    "catalysts": ["<string>", "<string>", ...],
    "warnings": ["<string>", "<string>", ...],
    "strategy": "<2-4 sentence action plan with specific instructions>",
    "best_entry_time": "<string, e.g. 'First 30 minutes' or 'After 10:30 AM pullback'>",
    "exit_strategy": "<string describing when/how to exit>"
}}

Return ONLY the JSON object. No markdown, no explanation, no code blocks.

Here is the intelligence briefing:

{briefing}"""


async def generate_trade_plan(ticker: str) -> dict:
    """Run intelligence sweep + LLM call to produce a structured trade plan.

    Returns a dict with the trade plan and raw briefing text.
    """
    from app.services.colonel_wolfe import run_intelligence_sweep

    # Phase 1: Intelligence sweep (reuses existing Col. Wolfe infrastructure)
    logger.info("Generating day-trade briefing for %s", ticker)
    try:
        briefing_text = await run_intelligence_sweep(ticker)
        logger.info("Intelligence briefing compiled for %s: %d chars", ticker, len(briefing_text))
    except Exception as e:
        logger.error("Intelligence sweep failed for %s: %s", ticker, e)
        return {"error": f"Intelligence sweep failed: {e}", "briefing": ""}

    # Phase 2: LLM call for structured trade plan
    try:
        import httpx

        api_key = settings.openai_api_key or settings.deepseek_api_key
        if not api_key:
            return {
                "error": "No API key configured. Set OPENAI_API_KEY in .env",
                "briefing": briefing_text,
            }

        prompt = TRADE_PLAN_PROMPT.format(briefing=briefing_text)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.deepseek_base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.quick_think_model,  # Use flash model for speed + cost
                    "messages": [
                        {"role": "system", "content": "You are a day-trading strategist. Return only valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,  # Lower temp for more consistent, precise output
                    "max_tokens": 2000,
                },
            )

        if resp.status_code != 200:
            logger.error("DeepSeek API error: %d %s", resp.status_code, resp.text[:500])
            return {
                "error": f"LLM API returned {resp.status_code}",
                "briefing": briefing_text,
            }

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Track token usage
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        # Estimate cost using DeepSeek pricing
        model = settings.quick_think_model
        pricing = {
            "deepseek-v4-flash": {"input": 0.07, "output": 0.14},
            "deepseek-v4-pro": {"input": 0.14, "output": 0.28},
            "deepseek-chat": {"input": 0.14, "output": 0.28},
        }
        rates = pricing.get(model, {"input": 0.50, "output": 1.50})
        cost_usd = Decimal(str(round(
            (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000, 6
        )))

        logger.info(
            "Briefing LLM call for %s: %d in / %d out tokens / $%.6f",
            ticker, input_tokens, output_tokens, float(cost_usd),
        )

        # Log cost to database so it shows on System Status page
        try:
            from app.database import async_session as async_session_factory
            from app.models import CostLog
            async with async_session_factory() as db:
                cost_entry = CostLog(
                    run_id=None,  # Briefings aren't tied to a run
                    provider="deepseek",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                )
                db.add(cost_entry)
                await db.commit()
                logger.info("Briefing cost logged: $%.6f", float(cost_usd))
        except Exception as e:
            logger.warning("Failed to log briefing cost: %s", e)

        # Parse the JSON response
        trade_plan = _parse_trade_plan(content, ticker)
        trade_plan["briefing"] = briefing_text
        trade_plan["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        trade_plan["ticker"] = ticker.upper()
        trade_plan["tokens_used"] = input_tokens + output_tokens
        trade_plan["cost_usd"] = float(cost_usd)

        return trade_plan

    except Exception as e:
        logger.error("Trade plan generation failed for %s: %s", ticker, e)
        return {
            "error": f"Trade plan generation failed: {e}",
            "briefing": briefing_text,
        }


def _parse_trade_plan(content: str, ticker: str) -> dict:
    """Parse LLM response into a clean trade plan dict.

    Handles various response formats and provides safe defaults.
    Uses multi-pass cleanup to handle common LLM JSON formatting issues.
    """
    import re

    # Strip markdown code blocks if present
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last lines (``` markers)
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        content = content.strip()

    def _clean_json(text: str) -> str:
        """Fix common LLM JSON quirks."""
        # Remove trailing commas before } or ]
        text = re.sub(r",\s*([}\]])", r"\1", text)
        # Remove single-line comments
        text = re.sub(r"//[^\n]*", "", text)
        # Replace single quotes with double quotes (carefully)
        # Only if the text doesn't already use double quotes properly
        if '"' not in text and "'" in text:
            text = text.replace("'", '"')
        # Remove any trailing text after the last }
        last_brace = text.rfind("}")
        if last_brace >= 0:
            text = text[:last_brace + 1]
        return text.strip()

    def _try_parse(text: str) -> dict | None:
        """Attempt JSON parse with progressive cleanup."""
        # Pass 1: Try raw
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Pass 2: Try cleaned
        cleaned = _clean_json(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # Pass 3: Extract JSON object from surrounding text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            extracted = text[start:end]
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                cleaned_extract = _clean_json(extracted)
                try:
                    return json.loads(cleaned_extract)
                except json.JSONDecodeError:
                    pass
        return None

    plan = _try_parse(content)
    if plan is None:
        logger.warning("Could not parse trade plan JSON for %s", ticker)
        return {
            "error": "Could not parse LLM response into a trade plan",
            "raw_response": content[:2000],
        }

    # Validate required fields and provide defaults
    defaults = {
        "direction": "NO TRADE",
        "confidence": 0,
        "thesis": "",
        "entry_low": 0,
        "entry_high": 0,
        "stop_loss": 0,
        "stop_loss_pct": 0,
        "target_1": 0,
        "target_1_pct": 0,
        "target_2": 0,
        "target_2_pct": 0,
        "target_3": 0,
        "target_3_pct": 0,
        "risk_reward": "N/A",
        "position_size_shares": 0,
        "position_size_dollars": 0,
        "key_supports": [],
        "key_resistances": [],
        "catalysts": [],
        "warnings": [],
        "strategy": "",
        "best_entry_time": "",
        "exit_strategy": "",
    }

    for key, default in defaults.items():
        if key not in plan:
            plan[key] = default

    return plan
