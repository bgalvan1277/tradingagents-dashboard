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
    "Thesis:", "Summary:", "Rationale:", or the first substantive sentence.
    """
    if not final_decision:
        return ""

    lines = final_decision.strip().split("\n")
    for line in lines:
        stripped = line.strip().lstrip("*#- ")
        lower = stripped.lower()
        # Look for labeled thesis lines
        for prefix in ["thesis:", "summary:", "rationale:", "recommendation:"]:
            if lower.startswith(prefix):
                thesis = stripped[len(prefix):].strip().lstrip("*: ")
                if len(thesis) > 10:
                    return thesis[:300]

    # Fallback: first line longer than 20 chars that isn't a header
    for line in lines:
        stripped = line.strip().lstrip("*#- ")
        if len(stripped) > 20 and not stripped.startswith("Rating"):
            return stripped[:300]

    return final_decision[:300]


def extract_state_to_detail(state: dict) -> dict:
    """Extract all structured fields from a TradingAgents state dict.

    Maps the state keys documented in agent_states.py into flat fields
    suitable for RunDetail columns.
    """
    invest_debate = state.get("investment_debate_state", {})
    risk_debate = state.get("risk_debate_state", {})

    # Build a clean copy of state for audit (exclude messages, they're huge)
    audit_state = {}
    for key in [
        "company_of_interest", "trade_date",
        "market_report", "sentiment_report", "news_report", "fundamentals_report",
        "investment_plan", "trader_investment_plan", "final_trade_decision",
    ]:
        if key in state:
            audit_state[key] = state[key]

    # Include debate states as dicts
    if invest_debate:
        audit_state["investment_debate_state"] = {
            k: v for k, v in invest_debate.items() if k != "count"
        }
    if risk_debate:
        audit_state["risk_debate_state"] = {
            k: v for k, v in risk_debate.items()
            if k not in ("count", "latest_speaker")
        }

    return {
        "market_report": state.get("market_report", ""),
        "sentiment_report": state.get("sentiment_report", ""),
        "news_report": state.get("news_report", ""),
        "fundamentals_report": state.get("fundamentals_report", ""),
        "bull_case_text": invest_debate.get("bull_history", ""),
        "bear_case_text": invest_debate.get("bear_history", ""),
        "debate_transcript": invest_debate.get("history", ""),
        "debate_judge_decision": invest_debate.get("judge_decision", ""),
        "risk_aggressive": risk_debate.get("aggressive_history", ""),
        "risk_conservative": risk_debate.get("conservative_history", ""),
        "risk_neutral": risk_debate.get("neutral_history", ""),
        "risk_transcript": risk_debate.get("history", ""),
        "risk_judge_decision": risk_debate.get("judge_decision", ""),
        "investment_plan": state.get("investment_plan", ""),
        "trader_investment_plan": state.get("trader_investment_plan", ""),
        "final_trade_decision": state.get("final_trade_decision", ""),
        "full_state_json": audit_state,
    }


def run_analysis_sync(ticker_symbol: str, trade_date: str) -> Tuple[dict, str]:
    """Run TradingAgents analysis synchronously.

    Returns (state_dict, decision_string).
    This must run in a separate process/thread since it makes many LLM calls.
    """
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    config.update(build_ta_config())

    ta = TradingAgentsGraph(debug=False, config=config)
    state, decision = ta.propagate(ticker_symbol, trade_date)

    return state, decision


async def save_run_results(
    db: AsyncSession,
    run: Run,
    state: dict,
    decision: str,
    cost_usd: Decimal = Decimal("0"),
) -> None:
    """Save a completed run's results to the database."""
    # Update the run record
    run.status = "complete"
    run.final_recommendation = decision
    run.one_line_thesis = extract_one_line_thesis(
        state.get("final_trade_decision", "")
    )
    run.total_cost_usd = cost_usd
    run.model_used = settings.deep_think_model

    # Extract and save detailed state
    detail_fields = extract_state_to_detail(state)
    detail = RunDetail(run_id=run.id, **detail_fields)
    db.add(detail)

    await db.commit()
    logger.info("Saved run %d for %s: %s", run.id, run.ticker_symbol, decision)


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
