"""Polymarket prediction analysis service.

Uses DeepSeek to analyze a Polymarket question through a structured
adversarial prompt that simulates the 6-agent pipeline:
  1. Nadia Petrova   – Intelligence gathering
  2. Lena Torres     – YES advocate
  3. Ryan Ashford    – NO advocate
  4. Derek Harmon    – Contrarian stress test
  5. Dr. Anika Patel – Probability synthesis
  6. Marco Chen      – Edge calculation
"""

import json
import logging
from decimal import Decimal

import httpx
from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"


def fetch_market_data(condition_id: str = None, slug: str = None) -> dict:
    """Fetch market data from Polymarket Gamma API."""
    try:
        if slug:
            resp = httpx.get(f"{GAMMA_BASE}/markets?slug={slug}", timeout=15)
        elif condition_id:
            resp = httpx.get(f"{GAMMA_BASE}/markets?id={condition_id}", timeout=15)
        else:
            return {}
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.error("Failed to fetch market data: %s", e)
        return {}


def run_poly_analysis_sync(question: str, yes_price: float, no_price: float,
                            volume: str = "", end_date: str = "",
                            market_slug: str = "") -> dict:
    """Run prediction market analysis synchronously via DeepSeek.

    Returns a dict with: ai_probability, edge, recommendation, reasoning, and agent sections.
    """
    client = OpenAI(
        api_key=settings.deepseek_api_key or settings.openai_api_key,
        base_url=settings.deepseek_base_url,
    )

    prompt = f"""You are a team of 6 specialized AI prediction market analysts. Analyze the following Polymarket prediction market and produce a structured consensus.

MARKET QUESTION: {question}
CURRENT ODDS: YES {yes_price:.0f}¢ / NO {no_price:.0f}¢
VOLUME: {volume}
END DATE: {end_date}
POLYMARKET URL: https://polymarket.com/event/{market_slug}

You must respond in EXACTLY this JSON format (no markdown, no code fences, just raw JSON):
{{
    "intelligence_briefing": "2-3 paragraph briefing on the topic from Nadia Petrova covering key facts, historical precedent, and current context",
    "yes_case": "2-3 paragraph argument for YES from Lena Torres with specific evidence and catalysts",
    "no_case": "2-3 paragraph argument for NO from Ryan Ashford with specific risks and barriers",
    "contrarian_note": "1-2 paragraph contrarian challenge from Derek Harmon identifying biases and blind spots",
    "ai_probability": <number between 0 and 100 representing your consensus YES probability>,
    "confidence": "<low|medium|high>",
    "synthesis": "2-3 paragraph probability synthesis from Dr. Anika Patel explaining the reasoning",
    "edge_analysis": "1-2 paragraph edge calculation from Marco Chen comparing AI probability to market price",
    "recommendation": "<STRONG BUY YES|BUY YES|HOLD|BUY NO|STRONG BUY NO>",
    "one_line_thesis": "One sentence summary of the consensus view"
}}

IMPORTANT RULES:
- ai_probability must be a number between 0 and 100
- Compare your ai_probability to the market's YES price ({yes_price:.0f}¢) to determine edge
- Edge = ai_probability - market YES price. If edge > +10, recommend BUY YES. If edge < -10, recommend BUY NO. Otherwise HOLD.
- If edge > +20 or < -20, use STRONG BUY
- Be rigorous, analytical, and data-driven. Do not hedge excessively.
- Consider base rates, historical precedent, and current evidence
"""

    try:
        response = client.chat.completions.create(
            model=settings.quick_think_model,
            messages=[
                {"role": "system", "content": "You are a prediction market analysis system. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
        )

        content = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3].strip()

        result = json.loads(content)

        # Extract usage
        usage = {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        # Estimate cost
        pricing = {"input": 0.07, "output": 0.14}  # flash pricing
        cost = (usage["input_tokens"] * pricing["input"] +
                usage["output_tokens"] * pricing["output"]) / 1_000_000
        usage["cost_usd"] = Decimal(str(round(cost, 6)))

        result["usage"] = usage
        result["status"] = "complete"

        # Ensure ai_probability is numeric
        try:
            result["ai_probability"] = float(result.get("ai_probability", 50))
        except (TypeError, ValueError):
            result["ai_probability"] = 50.0

        # Calculate edge
        result["edge"] = round(result["ai_probability"] - yes_price, 1)

        return result

    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM response as JSON: %s", e)
        return {
            "status": "failed",
            "error": f"JSON parse error: {e}",
            "ai_probability": 50,
            "edge": 0,
            "recommendation": "HOLD",
            "one_line_thesis": "Analysis failed to produce structured output",
        }
    except Exception as e:
        logger.error("Poly analysis failed: %s", e)
        return {
            "status": "failed",
            "error": str(e),
            "ai_probability": 50,
            "edge": 0,
            "recommendation": "HOLD",
            "one_line_thesis": f"Analysis error: {e}",
        }
