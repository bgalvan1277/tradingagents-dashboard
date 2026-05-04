"""Token usage tracker that intercepts httpx responses to DeepSeek API.

The openai SDK v1+ uses httpx internally for all HTTP requests. Rather than
trying to patch the SDK's create() method (which LangChain may bypass or
wrap), we patch httpx.Client.send() to intercept every HTTP response from
the DeepSeek completions endpoint and extract the usage data from the raw
JSON response body.

This is the most reliable approach because ALL API calls ultimately go
through httpx regardless of which LangChain abstraction layer is used.
"""

import json
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

# Endpoints to intercept
_COMPLETIONS_PATHS = ("/chat/completions", "/v1/chat/completions")


class TokenTracker:
    """Context manager that intercepts httpx responses to track token usage.

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
        self._original_send = None
        self._original_async_send = None
        self._patched = False

    def _accumulate_from_json(self, body: bytes, url: str):
        """Parse response body and extract usage data."""
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        usage = data.get("usage")
        if not usage:
            return

        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        total = usage.get("total_tokens", 0) or (prompt + completion)

        # Get model from response for accurate pricing
        resp_model = data.get("model", self.model_name) or self.model_name
        pricing = _PRICING.get(resp_model, _PRICING.get(self.model_name, _DEFAULT_PRICING))
        call_cost = (prompt * pricing["input"] + completion * pricing["output"]) / 1_000_000

        with self._lock:
            self.input_tokens += prompt
            self.output_tokens += completion
            self.total_tokens += total
            self.call_count += 1
            self.cost_usd += Decimal(str(round(call_cost, 6)))

        logger.info(
            "TokenTracker: +%d in / +%d out (model=%s, cost=$%.6f)",
            prompt, completion, resp_model, call_cost,
        )

    def _is_completions_url(self, url) -> bool:
        """Check if a URL is a chat completions endpoint."""
        url_str = str(url)
        return any(path in url_str for path in _COMPLETIONS_PATHS)

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
        """Monkey-patch httpx to intercept completions responses."""
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed, token tracking disabled")
            return

        tracker_ref = self

        # Patch sync httpx.Client.send
        try:
            original_send = httpx.Client.send
            self._original_send = original_send

            def patched_send(client_self, request, *args, **kwargs):
                response = original_send(client_self, request, *args, **kwargs)
                if tracker_ref._is_completions_url(request.url):
                    try:
                        # Read the response content
                        response.read()
                        tracker_ref._accumulate_from_json(response.content, str(request.url))
                    except Exception as e:
                        logger.debug("TokenTracker: failed to read sync response: %s", e)
                return response

            httpx.Client.send = patched_send
        except Exception as e:
            logger.warning("Failed to patch httpx.Client.send: %s", e)

        # Patch async httpx.AsyncClient.send
        try:
            original_async_send = httpx.AsyncClient.send
            self._original_async_send = original_async_send

            async def patched_async_send(client_self, request, *args, **kwargs):
                response = await original_async_send(client_self, request, *args, **kwargs)
                if tracker_ref._is_completions_url(request.url):
                    try:
                        await response.aread()
                        tracker_ref._accumulate_from_json(response.content, str(request.url))
                    except Exception as e:
                        logger.debug("TokenTracker: failed to read async response: %s", e)
                return response

            httpx.AsyncClient.send = patched_async_send
        except Exception as e:
            logger.warning("Failed to patch httpx.AsyncClient.send: %s", e)

        self._patched = True
        logger.info("TokenTracker: patched httpx client for usage tracking")

    def _unpatch(self):
        """Restore original httpx methods."""
        if not self._patched:
            return

        try:
            import httpx

            if self._original_send:
                httpx.Client.send = self._original_send
            if self._original_async_send:
                httpx.AsyncClient.send = self._original_async_send

            self._patched = False
            logger.info("TokenTracker: restored original httpx client")
        except Exception as e:
            logger.warning("Failed to unpatch httpx client: %s", e)

    def to_usage_dict(self) -> dict:
        """Return usage data in the same format runner.py expects."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
        }
