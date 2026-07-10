import time
import random
from threading import Lock
from datetime import datetime, timedelta, timezone
from fastapi import status, HTTPException


class DailyTokenBucket:
    def __init__(self, max_tokens, lock):
        self.max_tokens = max_tokens
        self.lock = lock()
        self.total_token = self.max_tokens
        today = datetime.utcnow().date().isoformat()
        self.last_reset = today

    def _reset_if_new_day(self):
        today = datetime.utcnow().date().isoformat()
        if today != self.last_reset:
            self.total_token = self.max_tokens
            self.last_reset = today

    def allow_request(self, token_to_consume: int = 1) -> bool:
        with self.lock:
            self._reset_if_new_day()
            if self.total_token >= token_to_consume:
                self.total_token -= token_to_consume
                return True
            return False

    def reset_time(self) -> str:
        with self.lock:
            today_utc = datetime.utcnow().date()
            tomorrow_utc = today_utc + timedelta(days=1)
            reset_datetime = datetime.combine(tomorrow_utc, datetime.min.time())
            return reset_datetime.isoformat() + "Z"


class TokenBucket:
    def __init__(self, max_tokens: int, refill_rate: int, interval: float, lock):
        assert max_tokens > 0, "max_tokens must be positive"
        assert refill_rate > 0, "refill_rate must be positive"
        assert interval > 0, "interval must be positive"
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.interval = interval
        self.lock = lock()
        self.total_token = self.max_tokens
        self.refilled_at = time.time()

    def _refill(self):
        elapsed = time.time() - self.refilled_at
        if elapsed >= self.interval:
            tokens_to_add = int(elapsed // self.interval) * self.refill_rate
            self.total_token = min(self.max_tokens, self.total_token + tokens_to_add)
            self.refilled_at += int(elapsed // self.interval) * self.interval

    def allow_request(self, token_to_consume: int = 1) -> bool:
        with self.lock:
            self._refill()
            if self.total_token >= token_to_consume:
                self.total_token -= token_to_consume
                return True
            return False

    def get_available_tokens(self) -> int:
        with self.lock:
            self._refill()
            return self.total_token

    def reset_time(self) -> float:
        with self.lock:
            return self.interval + self.refilled_at


class RateLimitExceededException(HTTPException):
    """Custom exception for when a rate limit is exceeded."""
    def __init__(self, detail: str, reset_time: float | str):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"X-Rate-Limit-Reset": str(reset_time)},
        )


class RateLimiter:
    def __init__(self, rpm_bucket: TokenBucket, rpd_bucket: DailyTokenBucket):
        self.rpm_bucket = rpm_bucket
        self.rpd_bucket = rpd_bucket

    def allow_request(self) -> bool:
        if not self.rpd_bucket.allow_request(1):
            reset_time = self.rpd_bucket.reset_time()
            raise RateLimitExceededException(detail="Daily request limit exceeded.", reset_time=reset_time)

        if not self.rpm_bucket.allow_request(1):
            reset_time = self.rpm_bucket.reset_time()
            raise RateLimitExceededException(detail="Per-minute request limit exceeded.", reset_time=reset_time)

        return True


class CircuitBreakerOpenException(Exception):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 30):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state = 'closed'
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.lock = Lock()

    def handle_failure(self):
        with self.lock:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                self.last_failure_time = time.time()

    def on_success(self):
        with self.lock:
            self.failure_count = 0
            # If it was half-open, it's now closed
            if self.state == 'half-open':
                self.state = 'closed'

    async def call(self, fn, *args, **kwargs):
        with self.lock:
            if self.state == 'open':
                if (time.time() - self.last_failure_time) >= self.reset_timeout:
                    self.state = 'half-open'
                else:
                    raise CircuitBreakerOpenException("Circuit breaker is currently open.")
        
        try:
            resp = await fn(*args, **kwargs)
            self.on_success()
            return resp
        except Exception as e:
            self.handle_failure()
            raise e

    def reset_time(self):
        with self.lock:
            if self.state == 'open':
                return self.last_failure_time + self.reset_timeout
            return time.time()