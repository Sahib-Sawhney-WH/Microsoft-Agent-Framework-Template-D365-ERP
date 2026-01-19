"""
Tests for D365 MCP Tool with circuit breaker and retry logic.

Covers:
- Circuit breaker functionality
- Retry logic with exponential backoff
- Token refresh on 401
- Connection management
- Tool invocation with session context
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
import asyncio
import time


# ==================== Test Fixtures ====================

@pytest.fixture
def mock_token_provider():
    """Mock D365 token provider."""
    provider = AsyncMock()
    provider.get_token = AsyncMock(return_value="test-access-token")
    provider.refresh_token = AsyncMock(return_value="refreshed-access-token")
    provider.close = AsyncMock()
    provider.environment_url = "https://test.operations.dynamics.com"
    return provider


@pytest.fixture
def mock_mcp_tool():
    """Mock MCPStreamableHTTPTool."""
    tool = AsyncMock()
    tool.tools = [
        {"name": "find_menu_item", "description": "Find menu item"},
        {"name": "open_form", "description": "Open a form"},
    ]
    tool.call_tool = AsyncMock(return_value={"success": True, "data": []})
    tool.__aenter__ = AsyncMock(return_value=tool)
    tool.__aexit__ = AsyncMock(return_value=False)
    return tool


@pytest.fixture
def mock_http_client():
    """Mock httpx AsyncClient."""
    client = AsyncMock()
    client.headers = {"Authorization": "Bearer test-token"}
    client.aclose = AsyncMock()
    return client


# ==================== Circuit Breaker Tests ====================

class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    @pytest.mark.asyncio
    async def test_circuit_starts_closed(self):
        """Test that circuit breaker starts in closed state."""
        from src.mcp.d365_tool import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)

        assert breaker.state == "closed"
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_successful_call_resets_failure_count(self):
        """Test that successful calls reset the failure counter."""
        from src.mcp.d365_tool import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3)
        breaker._failure_count = 2  # Simulate previous failures

        async def success():
            return "success"

        result = await breaker.call(success)

        assert result == "success"
        assert breaker.failure_count == 0
        assert breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_failures_increment_counter(self):
        """Test that failures increment the failure counter."""
        from src.mcp.d365_tool import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3)

        async def fail():
            raise Exception("Test error")

        for _ in range(2):
            with pytest.raises(Exception):
                await breaker.call(fail)

        assert breaker.failure_count == 2
        assert breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self):
        """Test that circuit opens after reaching failure threshold."""
        from src.mcp.d365_tool import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3)

        async def fail():
            raise Exception("Test error")

        for _ in range(3):
            with pytest.raises(Exception):
                await breaker.call(fail)

        assert breaker.state == "open"

    @pytest.mark.asyncio
    async def test_open_circuit_raises_exception(self):
        """Test that calls fail fast when circuit is open."""
        from src.mcp.d365_tool import CircuitBreaker, CircuitBreakerOpen

        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        breaker._state = "open"
        breaker._last_failure_time = time.time()

        async def success():
            return "success"

        with pytest.raises(CircuitBreakerOpen):
            await breaker.call(success)

    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open(self):
        """Test that circuit transitions to half-open after recovery timeout."""
        from src.mcp.d365_tool import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        breaker._state = "open"
        breaker._last_failure_time = time.time() - 1  # 1 second ago

        async def success():
            return "success"

        result = await breaker.call(success)

        assert result == "success"
        assert breaker.state == "closed"

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_circuit(self):
        """Test that failure in half-open state reopens the circuit."""
        from src.mcp.d365_tool import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        breaker._state = "open"
        breaker._last_failure_time = time.time() - 1  # Allow recovery

        async def fail():
            raise Exception("Still failing")

        with pytest.raises(Exception):
            await breaker.call(fail)

        assert breaker.state == "open"

    @pytest.mark.asyncio
    async def test_reset_closes_circuit(self):
        """Test that reset() closes the circuit."""
        from src.mcp.d365_tool import CircuitBreaker

        breaker = CircuitBreaker()
        breaker._state = "open"
        breaker._failure_count = 10

        breaker.reset()

        assert breaker.state == "closed"
        assert breaker.failure_count == 0


# ==================== D365MCPTool Tests ====================

class TestD365MCPTool:
    """Tests for D365MCPTool class."""

    @pytest.mark.asyncio
    async def test_initialization_requires_mcp_available(self):
        """Test that initialization fails without agent_framework."""
        with patch("src.mcp.d365_tool.MCP_AVAILABLE", False):
            from importlib import reload
            import src.mcp.d365_tool as d365_tool_module
            reload(d365_tool_module)

            with pytest.raises(ImportError, match="agent-framework is required"):
                d365_tool_module.D365MCPTool(
                    environment_url="https://test.operations.dynamics.com",
                    token_provider=MagicMock(),
                )

    @pytest.mark.asyncio
    async def test_initialization_requires_httpx(self):
        """Test that initialization fails without httpx."""
        with patch("src.mcp.d365_tool.MCP_AVAILABLE", True):
            with patch("src.mcp.d365_tool.HTTPX_AVAILABLE", False):
                from importlib import reload
                import src.mcp.d365_tool as d365_tool_module
                reload(d365_tool_module)

                with pytest.raises(ImportError, match="httpx is required"):
                    d365_tool_module.D365MCPTool(
                        environment_url="https://test.operations.dynamics.com",
                        token_provider=MagicMock(),
                    )

    @pytest.mark.asyncio
    async def test_connect_creates_http_client_with_token(
        self, mock_token_provider, mock_mcp_tool
    ):
        """Test that connect() creates HTTP client with OAuth token."""
        with patch("src.mcp.d365_tool.MCP_AVAILABLE", True):
            with patch("src.mcp.d365_tool.HTTPX_AVAILABLE", True):
                with patch("src.mcp.d365_tool.MCPStreamableHTTPTool", return_value=mock_mcp_tool):
                    with patch("src.mcp.d365_tool.AsyncClient") as MockClient:
                        mock_client = AsyncMock()
                        mock_client.aclose = AsyncMock()
                        MockClient.return_value = mock_client

                        from src.mcp.d365_tool import D365MCPTool

                        tool = D365MCPTool(
                            environment_url="https://test.operations.dynamics.com",
                            token_provider=mock_token_provider,
                        )

                        await tool.connect()

                        mock_token_provider.get_token.assert_called_once()
                        assert tool.is_connected

                        await tool.close()

    @pytest.mark.asyncio
    async def test_refresh_token_updates_http_client(
        self, mock_token_provider, mock_mcp_tool, mock_http_client
    ):
        """Test that refresh_token() updates the HTTP client header."""
        with patch("src.mcp.d365_tool.MCP_AVAILABLE", True):
            with patch("src.mcp.d365_tool.HTTPX_AVAILABLE", True):
                with patch("src.mcp.d365_tool.MCPStreamableHTTPTool", return_value=mock_mcp_tool):
                    with patch("src.mcp.d365_tool.AsyncClient", return_value=mock_http_client):
                        from src.mcp.d365_tool import D365MCPTool

                        tool = D365MCPTool(
                            environment_url="https://test.operations.dynamics.com",
                            token_provider=mock_token_provider,
                        )

                        await tool.connect()
                        await tool.refresh_token()

                        mock_token_provider.refresh_token.assert_called_once()

                        await tool.close()

    @pytest.mark.asyncio
    async def test_call_tool_requires_connection(self, mock_token_provider):
        """Test that call_tool raises error when not connected."""
        with patch("src.mcp.d365_tool.MCP_AVAILABLE", True):
            with patch("src.mcp.d365_tool.HTTPX_AVAILABLE", True):
                from src.mcp.d365_tool import D365MCPTool

                tool = D365MCPTool(
                    environment_url="https://test.operations.dynamics.com",
                    token_provider=mock_token_provider,
                )

                with pytest.raises(RuntimeError, match="Not connected"):
                    await tool.call_tool("find_menu_item", {"search_string": "test"})

    @pytest.mark.asyncio
    async def test_context_manager_lifecycle(
        self, mock_token_provider, mock_mcp_tool, mock_http_client
    ):
        """Test async context manager handles lifecycle correctly."""
        with patch("src.mcp.d365_tool.MCP_AVAILABLE", True):
            with patch("src.mcp.d365_tool.HTTPX_AVAILABLE", True):
                with patch("src.mcp.d365_tool.MCPStreamableHTTPTool", return_value=mock_mcp_tool):
                    with patch("src.mcp.d365_tool.AsyncClient", return_value=mock_http_client):
                        from src.mcp.d365_tool import D365MCPTool

                        tool = D365MCPTool(
                            environment_url="https://test.operations.dynamics.com",
                            token_provider=mock_token_provider,
                        )

                        async with tool:
                            assert tool.is_connected

                        assert not tool.is_connected

    @pytest.mark.asyncio
    async def test_properties(self, mock_token_provider):
        """Test tool properties."""
        with patch("src.mcp.d365_tool.MCP_AVAILABLE", True):
            with patch("src.mcp.d365_tool.HTTPX_AVAILABLE", True):
                from src.mcp.d365_tool import D365MCPTool

                tool = D365MCPTool(
                    name="d365-test",
                    environment_url="https://test.operations.dynamics.com",
                    token_provider=mock_token_provider,
                )

                assert tool.name == "d365-test"
                assert tool.environment_url == "https://test.operations.dynamics.com"
                assert tool.mcp_endpoint == "https://test.operations.dynamics.com/mcp"
                assert tool.is_connected is False
                assert tool.circuit_breaker.state == "closed"


# ==================== Retry Logic Tests ====================

class TestD365MCPToolRetry:
    """Tests for D365MCPTool retry logic."""

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(
        self, mock_token_provider, mock_mcp_tool, mock_http_client
    ):
        """Test that transient connection errors trigger retry."""
        call_count = [0]

        async def mock_call_tool(name, args):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("Network error")
            return {"success": True}

        mock_mcp_tool.call_tool = mock_call_tool

        with patch("src.mcp.d365_tool.MCP_AVAILABLE", True):
            with patch("src.mcp.d365_tool.HTTPX_AVAILABLE", True):
                with patch("src.mcp.d365_tool.MCPStreamableHTTPTool", return_value=mock_mcp_tool):
                    with patch("src.mcp.d365_tool.AsyncClient", return_value=mock_http_client):
                        from src.mcp.d365_tool import D365MCPTool

                        tool = D365MCPTool(
                            environment_url="https://test.operations.dynamics.com",
                            token_provider=mock_token_provider,
                            max_retries=3,
                            retry_backoff_base=0.01,  # Fast backoff for test
                        )

                        await tool.connect()
                        result = await tool.call_tool("test_tool", {})

                        assert result["success"] is True
                        assert call_count[0] == 3

                        await tool.close()

    @pytest.mark.asyncio
    async def test_gives_up_after_max_retries(
        self, mock_token_provider, mock_mcp_tool, mock_http_client
    ):
        """Test that retries stop after max_retries."""
        async def always_fail(name, args):
            raise ConnectionError("Persistent network error")

        mock_mcp_tool.call_tool = always_fail

        with patch("src.mcp.d365_tool.MCP_AVAILABLE", True):
            with patch("src.mcp.d365_tool.HTTPX_AVAILABLE", True):
                with patch("src.mcp.d365_tool.MCPStreamableHTTPTool", return_value=mock_mcp_tool):
                    with patch("src.mcp.d365_tool.AsyncClient", return_value=mock_http_client):
                        from src.mcp.d365_tool import D365MCPTool

                        tool = D365MCPTool(
                            environment_url="https://test.operations.dynamics.com",
                            token_provider=mock_token_provider,
                            max_retries=2,
                            retry_backoff_base=0.01,
                        )

                        await tool.connect()

                        with pytest.raises(ConnectionError):
                            await tool.call_tool("test_tool", {})

                        await tool.close()


# ==================== Error Handling Tests ====================

class TestD365MCPToolErrors:
    """Tests for D365MCPTool error handling."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_repeated_failures(
        self, mock_token_provider, mock_mcp_tool, mock_http_client
    ):
        """Test that circuit breaker opens after repeated failures."""
        async def always_fail(name, args):
            raise Exception("Service unavailable")

        mock_mcp_tool.call_tool = always_fail

        with patch("src.mcp.d365_tool.MCP_AVAILABLE", True):
            with patch("src.mcp.d365_tool.HTTPX_AVAILABLE", True):
                with patch("src.mcp.d365_tool.MCPStreamableHTTPTool", return_value=mock_mcp_tool):
                    with patch("src.mcp.d365_tool.AsyncClient", return_value=mock_http_client):
                        from src.mcp.d365_tool import D365MCPTool, CircuitBreakerOpen

                        tool = D365MCPTool(
                            environment_url="https://test.operations.dynamics.com",
                            token_provider=mock_token_provider,
                            max_retries=0,  # No retries
                            circuit_breaker_failure_threshold=3,
                            circuit_breaker_recovery_timeout=60.0,
                        )

                        await tool.connect()

                        # Trigger failures to open circuit
                        for _ in range(3):
                            try:
                                await tool.call_tool("test_tool", {})
                            except Exception:
                                pass

                        # Next call should fail with CircuitBreakerOpen
                        with pytest.raises(CircuitBreakerOpen):
                            await tool.call_tool("test_tool", {})

                        await tool.close()
