"""TradingAgents wrapper: runs analysis and extracts structured state into DB rows.

This is the hardest part of the integration. The TradingAgents framework returns
a rich state object from propagate() that contains individual agent reports,
debate transcripts, and the final decision. This module decomposes that state
into structured database fields so the UI can render each section independently.
"""

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Run, RunDetail, CostLog

logger = logging.getLogger(__name__)


def build_ta_config() -> dict:
    """Build the TradingAgents config dict from our settings."""
    return {
        "llm_provider": "deepseek",
        "deep_think_llm": settings.deep_think_model,
        "quick_think_llm": settings.quick_think_model,
        "max_debate_rounds": settings.max_debate_rounds,
        "max_risk_discuss_rounds": settings.max_risk_discuss_rounds,
        "checkpoint_enabled": False,
        "data_vendors": {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "yfinance",
            "news_data": "yfinance",
        },
    }


def extract_one_line_thesis(final_decision: str) -> str:
    """Extract a one-line thesis from the PM's decision text.

    Looks for common patterns in the structured output: a line starting with
    "Thesis:", "Summary:", "Rationale:", or actionable section headings like
    "Actionable Execution", "Decisive Action Plan", "Portfolio Directive".
    Falls back to the first substantive sentence that isn't a redundant label.
    """
    if not final_decision:
        return ""

    lines = final_decision.strip().split("\n")

    # Pass 1: Look for labeled thesis/summary/rationale lines
    for line in lines:
        stripped = line.strip().lstrip("*#- ")
        lower = stripped.lower()
        for prefix in ["thesis:", "summary:", "rationale:", "recommendation:"]:
            if lower.startswith(prefix):
                thesis = stripped[len(prefix):].strip().lstrip("*: ")
                if len(thesis) > 10 and not thesis.lower().startswith("final trading decision"):
                    return thesis[:300]

    # Pass 2: Look for actionable section headings and grab the first sentence after
    action_headings = [
        "actionable execution", "decisive action plan", "decisive action",
        "portfolio directive", "recommended action", "action plan",
        "immediate action", "position action", "trade action",
    ]
    in_action_section = False
    for line in lines:
        stripped = line.strip().lstrip("*#- ")
        lower = stripped.lower()
        if any(h in lower for h in action_headings):
            in_action_section = True
            continue
        if in_action_section:
            cleaned = stripped.lstrip("*#-•· ").rstrip("*")
            if len(cleaned) > 15 and not cleaned.lower().startswith("final trading decision"):
                return cleaned[:300]
            if stripped == "" or stripped.startswith("#"):
                in_action_section = False

    # Pass 3: Fallback to first substantive line that isn't redundant
    for line in lines:
        stripped = line.strip().lstrip("*#- ")
        if (
            len(stripped) > 20
            and not stripped.startswith("Rating")
            and not stripped.lower().startswith("final trading decision")
            and not stripped.lower().startswith("decision:")
        ):
            return stripped[:300]

    return final_decision[:300]


def _to_str(val) -> str:
    """Convert any value to a string suitable for a Text column.

    TradingAgents returns lists-of-strings for debate histories,
    dicts for some fields, and plain strings for others.
    """
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return "\n\n".join(str(item) for item in val)
    if isinstance(val, dict):
        try:
            return json.dumps(val, indent=2, default=str)
        except (TypeError, ValueError):
            return str(val)
    return str(val)


def _make_json_safe(obj):
    """Recursively convert an object to JSON-safe primitives."""
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_safe(item) for item in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


def extract_state_to_detail(state: dict) -> dict:
    """Extract all structured fields from a TradingAgents state dict.

    Maps the state keys documented in agent_states.py into flat fields
    suitable for RunDetail columns.
    """
    invest_debate = state.get("investment_debate_state", {})
    risk_debate = state.get("risk_debate_state", {})

    if not isinstance(invest_debate, dict):
        invest_debate = {}
    if not isinstance(risk_debate, dict):
        risk_debate = {}

    # Build a clean copy of state for audit (exclude messages, they're huge)
    audit_state = {}
    for key in [
        "company_of_interest", "trade_date",
        "market_report", "sentiment_report", "news_report", "fundamentals_report",
        "investment_plan", "trader_investment_plan", "final_trade_decision",
    ]:
        if key in state:
            audit_state[key] = _to_str(state[key])

    # Include debate states as dicts
    if invest_debate:
        audit_state["investment_debate_state"] = {
            k: _to_str(v) for k, v in invest_debate.items() if k != "count"
        }
    if risk_debate:
        audit_state["risk_debate_state"] = {
            k: _to_str(v) for k, v in risk_debate.items()
            if k not in ("count", "latest_speaker")
        }

    return {
        "intelligence_briefing": _to_str(state.get("intelligence_briefing", "")),
        "market_report": _to_str(state.get("market_report", "")),
        "sentiment_report": _to_str(state.get("sentiment_report", "")),
        "news_report": _to_str(state.get("news_report", "")),
        "fundamentals_report": _to_str(state.get("fundamentals_report", "")),
        "bull_case_text": _to_str(invest_debate.get("bull_history", "")),
        "bear_case_text": _to_str(invest_debate.get("bear_history", "")),
        "debate_transcript": _to_str(invest_debate.get("history", "")),
        "debate_judge_decision": _to_str(invest_debate.get("judge_decision", "")),
        "risk_aggressive": _to_str(risk_debate.get("aggressive_history", "")),
        "risk_conservative": _to_str(risk_debate.get("conservative_history", "")),
        "risk_neutral": _to_str(risk_debate.get("neutral_history", "")),
        "risk_transcript": _to_str(risk_debate.get("history", "")),
        "risk_judge_decision": _to_str(risk_debate.get("judge_decision", "")),
        "investment_plan": _to_str(state.get("investment_plan", "")),
        "trader_investment_plan": _to_str(state.get("trader_investment_plan", "")),
        "final_trade_decision": _to_str(state.get("final_trade_decision", "")),
        "full_state_json": _make_json_safe(audit_state),
    }


# DeepSeek pricing per million tokens (as of 2025)
_DEEPSEEK_PRICING = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # v4 models
    "deepseek-v4-pro": {"input": 0.14, "output": 0.28},
    "deepseek-v4-flash": {"input": 0.07, "output": 0.14},
}
_DEFAULT_PRICING = {"input": 0.50, "output": 1.50}  # fallback


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Estimate cost in USD from token counts using published pricing."""
    pricing = _DEEPSEEK_PRICING.get(model, _DEFAULT_PRICING)
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    return Decimal(str(round(cost, 6)))


def run_analysis_sync(ticker_symbol: str, trade_date: str) -> Tuple[dict, str, dict]:
    """Run TradingAgents analysis synchronously.

    Returns (state_dict, decision_string, usage_dict).
    usage_dict contains: input_tokens, output_tokens, total_tokens, cost_usd.
    This must run in a separate process/thread since it makes many LLM calls.

    Phase 0 (Col. Wolfe): Intelligence sweep runs first, collecting OSINT data.
    Phase 1-4 (TradingAgents): The intelligence briefing is injected into the
    agent state so all downstream analysts have access to it.
    """
    import asyncio
    from app.services.colonel_wolfe import run_intelligence_sweep
    from app.services.token_tracker import TokenTracker

    # Phase 0: Colonel Wolfe's Intelligence Sweep
    logger.info("Phase 0: Col. Wolfe intelligence sweep for %s", ticker_symbol)
    try:
        intel_briefing = asyncio.run(run_intelligence_sweep(ticker_symbol))
        logger.info("Intelligence briefing compiled: %d chars", len(intel_briefing))
    except Exception as e:
        logger.error("Intelligence sweep failed for %s: %s", ticker_symbol, e)
        intel_briefing = f"Intelligence sweep failed: {e}"

    # Phase 1-4: TradingAgents Pipeline with cost tracking
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config.update(build_ta_config())

    ta = TradingAgentsGraph(debug=False, config=config)

    # Track token usage by intercepting OpenAI-compatible API responses
    tracker = TokenTracker(model_name=settings.deep_think_model)
    try:
        with tracker:
            state, decision = ta.propagate(ticker_symbol, trade_date)
        usage = tracker.to_usage_dict()
        logger.info(
            "LLM usage for %s: %d in / %d out / %d calls / $%.6f",
            ticker_symbol, usage["input_tokens"], usage["output_tokens"],
            tracker.call_count, float(usage["cost_usd"]),
        )
    except Exception as e:
        logger.error("Analysis failed for %s: %s", ticker_symbol, e)
        raise

    # Inject the intelligence briefing into the state for storage
    state["intelligence_briefing"] = intel_briefing

    return state, decision, usage


async def save_run_results(
    db: AsyncSession,
    run: Run,
    state: dict,
    decision: str,
    cost_usd: Decimal = Decimal("0"),
    usage: dict = None,
) -> None:
    """Save a completed run's results to the database."""
    # Use usage-derived cost if available
    if usage and usage.get("cost_usd"):
        cost_usd = usage["cost_usd"]

    # Update the run record first
    run.status = "complete"
    run.final_recommendation = decision
    run.one_line_thesis = extract_one_line_thesis(
        _to_str(state.get("final_trade_decision", ""))
    )
    run.total_cost_usd = cost_usd
    run.model_used = settings.deep_think_model
    await db.commit()
    logger.info("Marked run %d for %s as complete: %s", run.id, run.ticker_symbol, decision)

    # Log cost entry if we have usage data
    if usage and (usage.get("input_tokens", 0) > 0 or usage.get("output_tokens", 0) > 0):
        try:
            cost_entry = CostLog(
                run_id=run.id,
                provider="deepseek",
                model=settings.deep_think_model,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cost_usd=cost_usd,
            )
            db.add(cost_entry)
            await db.commit()
            logger.info(
                "Logged cost for run %d: %d in / %d out / $%.6f",
                run.id, usage.get("input_tokens", 0),
                usage.get("output_tokens", 0), float(cost_usd),
            )
        except Exception as e:
            logger.error("Failed to log cost for run %d: %s", run.id, e)
            await db.rollback()

    # Now save the detailed state (separate commit so Run is always saved)
    try:
        detail_fields = extract_state_to_detail(state)
        detail = RunDetail(run_id=run.id, **detail_fields)
        db.add(detail)
        await db.commit()
        logger.info("Saved RunDetail for run %d", run.id)
    except Exception as e:
        logger.error("Failed to save RunDetail for run %d: %s", run.id, e)
        await db.rollback()


async def mark_run_failed(
    db: AsyncSession,
    run: Run,
    error_message: str,
) -> None:
    """Mark a run as failed with an error message."""
    run.status = "failed"
    run.error_message = error_message[:2000]
    await db.commit()
    logger.error("Run %d for %s failed: %s", run.id, run.ticker_symbol, error_message)
