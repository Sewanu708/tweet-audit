import time
from .logger import logger
from threading import Lock
from datetime import datetime, timedelta
from fastapi import status, HTTPException
from redis import Redis


class DailyTokenBucket:
    def __init__(self, max_tokens: int, lock, redis_client, key: str = "daily_token_bucket"):
        self.max_tokens = max_tokens
        self.lock = lock()
        self.redis_client = redis_client
        self.key = key
        self._update_state_from_redis()

    def _update_state_from_redis(self):
        state = self.redis_client.hgetall(self.key)
        today = datetime.utcnow().date().isoformat()
        if not state or state.get('last_reset') != today:
            self.total_token = self.max_tokens
            self.last_reset = today
            self.redis_client.hset(self.key, mapping={
                "total_token": self.total_token,
                "last_reset": self.last_reset
            })
        else:
            self.total_token = int(state.get('total_token', self.max_tokens))
            self.last_reset = state.get('last_reset', today)

    def allow_request(self, token_to_consume: int = 1) -> bool:
        with self.lock:
            self._update_state_from_redis()  
            if self.total_token >= token_to_consume:
                self.total_token -= token_to_consume
                self.redis_client.hset(self.key, "total_token", self.total_token)
                return True
            return False

    def reset_time(self) -> str:
        today_utc = datetime.utcnow().date()
        tomorrow_utc = today_utc + timedelta(days=1)
        reset_datetime = datetime.combine(tomorrow_utc, datetime.min.time())
        return reset_datetime.isoformat() + "Z"


class TokenBucket:
    def __init__(self, max_tokens: int, refill_rate: int, interval: float, lock, redis_client, key: str = "token_bucket"):
        assert max_tokens > 0, "max_tokens must be positive"
        assert refill_rate > 0, "refill_rate must be positive"
        assert interval > 0, "interval must be positive"
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.interval = interval
        self.redis_client = redis_client
        self.key = key
        self.lock = lock()
        self.total_token = self.max_tokens
        self.refilled_at = time.time()

    def _refill(self):
        elapsed = time.time() - self.refilled_at
        if elapsed >= self.interval:
            tokens_to_add = int(elapsed // self.interval) * self.refill_rate
            self.total_token = min(self.max_tokens, self.total_token + tokens_to_add)
            self.refilled_at += int(elapsed // self.interval) * self.interval

    def _update_state_from_redis(self):
        state = self.redis_client.hgetall(self.key)
        if not state:
            self.total_token = self.max_tokens
            self.refilled_at = time.time()
            self.redis_client.hset(self.key, mapping={"total_token": self.total_token, "refilled_at": self.refilled_at})
        else:
            self.total_token = int(state.get('total_token', self.max_tokens))
            self.refilled_at = float(state.get('refilled_at', time.time()))

    def allow_request(self, token_to_consume: int = 1) -> bool:
        with self.lock:
            self._update_state_from_redis()
            self._refill()
            if self.total_token >= token_to_consume:
                self.total_token -= token_to_consume
                self.redis_client.hset(self.key, mapping={"total_token": self.total_token, "refilled_at": self.refilled_at})
                return True
            return False

    def get_available_tokens(self) -> int:
        with self.lock:
            self._update_state_from_redis()
            self._refill()
            return self.total_token

    def reset_time(self) -> float:
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
    def __init__(self, redis_client:Redis,  failure_threshold: int = 5, reset_timeout: int = 30, key: str = "circuit_breaker"):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.redis_client = redis_client
        self.key = key
        self.lock = Lock()
        self.update_from_store()
    
    def update_from_store(self):
        state = self.redis_client.hgetall(self.key)
        if not state:
            self.state = 'closed'
            self.failure_count = 0
            self.last_failure_time = 0.0
            self.redis_client.hset(self.key, mapping={
                "state": self.state,
                "failure_count": self.failure_count,
                "last_failure_time": self.last_failure_time
            })
        else:
            self.state = state.get('state', 'closed')
            self.failure_count = int(state.get('failure_count', 0))
            self.last_failure_time = float(state.get('last_failure_time', 0.0))

        
    def handle_failure(self):
        with self.lock:
            self.update_from_store()
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                self.last_failure_time = time.time()
            self.redis_client.hset(self.key, mapping={"failure_count": self.failure_count, "state": self.state, "last_failure_time": self.last_failure_time})

    def on_success(self):
        with self.lock:
            if self.state == 'half-open' or self.failure_count > 0:
                self.state = 'closed'
                self.failure_count = 0
                self.redis_client.hset(self.key, mapping={"state": self.state, "failure_count": self.failure_count})

    async def call(self, fn, *args, **kwargs):
        self.update_from_store()
        if self.state == 'open':
            if (time.time() - self.last_failure_time) >= self.reset_timeout:
                self.state = 'half-open'
                self.redis_client.hset(self.key, "state", self.state)
            else:
                raise CircuitBreakerOpenException("Circuit breaker is currently open.")
        
        try:
            logger.info("Call fired to downstream service")
            resp = await fn(*args, **kwargs)
            self.on_success()
            return resp
        except Exception as e:
            self.handle_failure()
            raise e

    def reset_time(self):
        if self.state == 'open':
            return self.last_failure_time + self.reset_timeout
        return time.time()