from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from src.resilience import (
    CircuitBreakerOpenException,
    RateLimitExceededException,
)


@pytest.mark.anyio(backend='asyncio')
@patch("src.agent.time.sleep", return_value=None)  
async def test_call_handles_500_error_with_retries(mock_sleep, agent, mock_rate_limiter, mock_circuit_breaker):
    """
    Tests that the `call` method retries on 500-level HTTP errors and eventually fails.
    """
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    http_error = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=mock_response
    )
    agent.client.post = AsyncMock(side_effect=http_error)

    max_retries = 3
    expected_calls = max_retries + 1

    response = await agent.call("http://localhost:4000", {})

    assert agent.client.post.call_count == expected_calls
    assert mock_sleep.call_count == max_retries  
    assert not response.success
    assert response.response_code == 500
    assert "Server Error" in response.err_message


@pytest.mark.anyio(backend='asyncio')
@patch("src.agent.time.sleep", return_value=None)
async def test_call_handles_403_error_without_retry(mock_sleep, agent, mock_rate_limiter):
    """
    Tests that the `call` method fails immediately on a 403 client error without retrying.
    """
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 403
    http_error = httpx.HTTPStatusError(
        "Forbidden", request=MagicMock(), response=mock_response
    )
    agent.client.post = AsyncMock(side_effect=http_error)

    response = await agent.call("http://localhost:4000", {})

    assert agent.client.post.call_count == 1
    assert mock_sleep.call_count == 0
    assert not response.success
    assert response.response_code == 403
    assert "Forbidden" in response.err_message


@pytest.mark.anyio(backend='asyncio')
@patch("src.agent.time.sleep", return_value=None)
@patch("src.agent._resolve_sleep_time", return_value=1)
async def test_call_handles_rate_limit_429(mock_resolve_sleep, mock_sleep, agent, mock_rate_limiter):
    """
    Tests that the `call` method waits and retries when a RateLimitExceededException (429) is raised.
    """
    rate_limit_exc = RateLimitExceededException(
        detail="Per-minute request limit exceeded.", reset_time="1234567890"
    )
    mock_rate_limiter.allow_request.side_effect = [
        rate_limit_exc,
        True,  
    ]

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"result": "ok"}
    agent.client.post = AsyncMock(return_value=mock_response)

    response = await agent.call("http://test.url", {})

    assert mock_rate_limiter.allow_request.call_count == 2
    assert mock_sleep.call_count == 1  
    assert agent.client.post.call_count == 1
    assert response.success
    assert response.response_code == 200
    assert response.data == {"result": "ok"}


@pytest.mark.anyio(backend='asyncio')
async def test_call_respects_open_circuit_breaker(agent, mock_rate_limiter, mock_circuit_breaker):
    """
    Tests that the `call` method fails fast if the circuit breaker is open.
    """
    # Simulate an open circuit breaker
    breaker_exc = CircuitBreakerOpenException("Circuit breaker is currently open.")
    mock_circuit_breaker.call.side_effect = breaker_exc

    agent.client.post = AsyncMock()

    with pytest.raises(CircuitBreakerOpenException):
        await agent.call("http://test.url", {})

    # Ensure no external call was made
    assert agent.client.post.call_count == 0
    # The rate limiter is checked before the breaker, so it will be called once
    assert mock_rate_limiter.allow_request.call_count == 1


@pytest.mark.anyio(backend='asyncio')
async def test_call_respects_token_bucket_and_succeeds(agent, mock_rate_limiter):
    """
    Tests that a successful call correctly consumes a token from the rate limiter.
    """
    # Mock a successful API call
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "success"}
    agent.client.post = AsyncMock(return_value=mock_response)

    response = await agent.call("http://test.url", {})

    # Verify that the rate limiter was checked
    mock_rate_limiter.allow_request.assert_called_once()

    # Verify the call was successful
    assert agent.client.post.call_count == 1
    assert response.success
    assert response.response_code == 200
    assert response.data == {"data": "success"}


@pytest.mark.anyio(backend='asyncio')
@patch("src.agent.time.sleep", return_value=None)
async def test_call_succeeds_on_first_try(mock_sleep, agent, mock_rate_limiter):
    """
    Tests the happy path where the call succeeds on the first attempt without any errors.
    """
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "success"}
    agent.client.post = AsyncMock(return_value=mock_response)

    response = await agent.call("http://test.url", {})

    assert mock_rate_limiter.allow_request.call_count == 1
    assert agent.client.post.call_count == 1
    assert mock_sleep.call_count == 0
    assert response.success
    assert response.response_code == 200
    assert response.data == {"data": "success"}