import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    RateLimitExceededException,
    RateLimiter,
)
from src.agent import AgentDownStream, AgentResponse

@pytest.fixture(scope="session")
def anyio_backend():
    # use asyncio for all async runs
    return "asyncio"

@pytest.fixture
def mock_rate_limiter():
    """Fixture for a mock RateLimiter."""
    return MagicMock(spec=RateLimiter)


@pytest.fixture
def mock_circuit_breaker():
    """Fixture for a mock CircuitBreaker."""
    breaker = MagicMock(spec=CircuitBreaker)

    async def mock_breaker_call(func, *args, **kwargs):
        return await func(*args, **kwargs)

    breaker.call.side_effect = mock_breaker_call
    return breaker


@pytest.fixture
def agent(mock_rate_limiter, mock_circuit_breaker):
    """Fixture to create an AgentDownStream instance with mocks."""
    return AgentDownStream(
        rate_limiter=mock_rate_limiter,
        breaker=mock_circuit_breaker,
        api_key="test_api_key",
    )
