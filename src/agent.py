import asyncio
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, Optional

import httpx
from logger import logger

from resilience import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    RateLimitExceededException,
    RateLimiter,
)


class AgentException(Exception):
    """Custom exception for agent-related failures."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict | str] = None):
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(message)


@dataclass
class AgentResponse:
    """Standard response structure for agent calls."""
    success: bool
    response_code: int
    data: list[Dict[str, Any]]
    err_message: str | None = None


def backoff(base_delay: int, multiplier: int, attempt: int = 0, max_delay: int = 60):
    """Exponential backoff with jitter."""
    exponential_delay = base_delay * (multiplier**attempt)
    max_capped_delay = min(exponential_delay, max_delay)
    return random.uniform(0, max_capped_delay)


def _resolve_sleep_time(reset_time_str: str) -> float:
    """Calculates sleep duration from a rate-limit reset header."""
    try:
        reset_timestamp = float(reset_time_str)
        return max(0, reset_timestamp - time.time())
    except (ValueError, TypeError):
        reset_dt = datetime.fromisoformat(reset_time_str.replace("Z", "+00:00"))
        return (reset_dt - datetime.now(timezone.utc)).total_seconds()


def ag_retry(max_retry: int):
    """
    A decorator that adds rate limiting, circuit breaking, and retry logic
    with exponential backoff to a function making external HTTP calls.
    """
    def decorator(func):
        @wraps(func)
        def main_logic(self, *args, **kwargs):
            attempts = 0
            while attempts <= max_retry:
                try:
                    self.rate_limiter.allow_request()
                    return self.breaker.call(func, self, *args, **kwargs)

                except RateLimitExceededException as e:
                    reset_time_str = e.headers.get("X-Rate-Limit-Reset")
                    logger.warning(f"Rate limit hit: {e.detail}. Waiting for reset at {reset_time_str}.")
                    sleep_for = _resolve_sleep_time(reset_time_str)
                    time.sleep(max(0, sleep_for + 1))  
                    continue  

                except CircuitBreakerOpenException as e:
                    logger.error(f"Circuit breaker is open. Failing fast. Error: {e}")
                    raise  

                except httpx.HTTPStatusError as e:
                    if 400 <= e.response.status_code < 500:
                        logger.error(f"Client error {e.response.status_code}: {e.request.url}. Failing fast.")
                        raise  

                    attempts += 1
                    if attempts > max_retry:
                        logger.error(f"Max retries ({max_retry}) exceeded. Failing job. Last error: {e}")
                        return AgentResponse(success=False, response_code=e.response.status_code, data=[], err_message=str(e))

                    sleep_time = backoff(base_delay=1, multiplier=2, attempt=attempts)
                    logger.warning(f"Attempt {attempts}/{max_retry} failed with error: {e}. Retrying in {sleep_time:.2f} seconds.")
                    time.sleep(sleep_time)

                except Exception as e:
                    logger.error(f"An unexpected error occurred: {e}", exc_info=True)
                    # Assuming unexpected errors are not retriable
                    return AgentResponse(success=False, response_code=500, data=[], err_message=str(e))

        return main_logic
    return decorator


class AgentDownStream:
    """A resilient agent for making downstream API calls."""
    def __init__(self, rate_limiter: RateLimiter, breaker: CircuitBreaker, api_key: str):
        self.rate_limiter = rate_limiter
        self.breaker = breaker
        self.api_key = api_key
        self.client = httpx.Client(
            headers={"Content-Type": "application/json"},
            params={"key": self.api_key}
        )

    @ag_retry(max_retry=3)
    def call(self, url: str, payload: dict) -> AgentResponse:
        response = self.client.post(url, json=payload, timeout=300)
        response.raise_for_status()  # Will raise HTTPStatusError on 4xx/5xx
        return AgentResponse(success=True, response_code=response.status_code, data=response.json())