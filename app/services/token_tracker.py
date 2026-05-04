"""Token usage tracker that intercepts OpenAI-compatible API responses.

The LangChain get_openai_callback only works with OpenAI-native models.
DeepSeek (and other OpenAI-compatible providers) return usage data in the
same response format, but the callback ignores non-OpenAI model names.

This module monkey-patches the openai client's chat.completions.create
method to intercept every response and accumulate token counts from the
usage field that every OpenAI-compatible API returns.
"""

import logging
import threading
from decimal import Decimal

logger = logging.getLogger(__name__)


# DeepSeek pricing per million tokens
_PRICING = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    "deepseek-v4-pro": {"input": 0.14, "output": 0.28},
    "deepseek-v4-flash": {"input": 0.07, "output": 0.14},
}
_DEFAULT_PRICING = {"input": 0.50, "output": 1.50}


class TokenTracker:
    """Context manager that intercepts OpenAI-compatible API calls to track tokens.

    Usage:
        tracker = TokenTracker()
        with tracker:
            # run LLM pipeline
            ...
        print(tracker.input_tokens, tracker.output_tokens, tracker.cost_usd)
    """

    def __init__(self, model_name: str = "deepseek-chat"):
        self.model_name = model_name
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.call_count = 0
        self.cost_usd = Decimal("0")
        self._lock = threading.Lock()
        self._original_create = None
        self._original_async_create = None
        self._patched = False

    def _accumulate(self, response):
        """Extract usage from an API response and accumulate totals."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return

        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        total = getattr(usage, "total_tokens", 0) or (prompt + completion)

        # Detect the model from the response for accurate pricing
        resp_model = getattr(response, "model", self.model_name) or self.model_name

        pricing = _PRICING.get(resp_model, _PRICING.get(self.model_name, _DEFAULT_PRICING))
        call_cost = (prompt * pricing["input"] + completion * pricing["output"]) / 1_000_000

        with self._lock:
            self.input_tokens += prompt
            self.output_tokens += completion
            self.total_tokens += total
            self.call_count += 1
            self.cost_usd += Decimal(str(round(call_cost, 6)))

        logger.debug(
            "TokenTracker: +%d in / +%d out (model=%s, cost=$%.6f)",
            prompt, completion, resp_model, call_cost,
        )

    def __enter__(self):
        self._patch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._unpatch()
        logger.info(
            "TokenTracker totals: %d in / %d out / %d calls / $%.6f",
            self.input_tokens, self.output_tokens, self.call_count, self.cost_usd,
        )
        return False

    def _patch(self):
        """Monkey-patch the openai client to intercept responses."""
        try:
            import openai
        except ImportError:
            logger.warning("openai package not installed, token tracking disabled")
            return

        # Patch sync create
        try:
            original_sync = openai.resources.chat.completions.Completions.create

            tracker_ref = self

            def patched_create(self_inner, *args, **kwargs):
                response = original_sync(self_inner, *args, **kwargs)
                tracker_ref._accumulate(response)
                return response

            openai.resources.chat.completions.Completions.create = patched_create
            self._original_create = original_sync
        except Exception as e:
            logger.warning("Failed to patch sync create: %s", e)

        # Patch async create
        try:
            original_async = openai.resources.chat.completions.AsyncCompletions.create

            tracker_ref = self

            async def patched_async_create(self_inner, *args, **kwargs):
                response = await original_async(self_inner, *args, **kwargs)
                tracker_ref._accumulate(response)
                return response

            openai.resources.chat.completions.AsyncCompletions.create = patched_async_create
            self._original_async_create = original_async
        except Exception as e:
            logger.warning("Failed to patch async create: %s", e)

        self._patched = True
        logger.info("TokenTracker: patched openai client for usage tracking")

    def _unpatch(self):
        """Restore the original openai client methods."""
        if not self._patched:
            return

        try:
            import openai

            if self._original_create:
                openai.resources.chat.completions.Completions.create = self._original_create
            if self._original_async_create:
                openai.resources.chat.completions.AsyncCompletions.create = self._original_async_create

            self._patched = False
            logger.info("TokenTracker: restored original openai client")
        except Exception as e:
            logger.warning("Failed to unpatch openai client: %s", e)

    def to_usage_dict(self) -> dict:
        """Return usage data in the same format runner.py expects."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
        }
