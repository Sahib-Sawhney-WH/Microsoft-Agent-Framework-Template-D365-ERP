"""
D365 F&O MCP tool using SDK's MCPStreamableHTTPTool with custom OAuth.

Wraps the Agent Framework SDK's MCPStreamableHTTPTool with D365-specific
OAuth token injection and session context management.

Production hardening features:
- Retry logic with automatic 401 token refresh
- Circuit breaker for fault tolerance
- OpenTelemetry tracing and metrics
- Proper httpx timeout configuration

Key D365 MCP Behaviors:
- 25 Row Limit: D365 MCP returns max 25 rows - results indicate if limit was hit
- Object Names: Use object names (not labels) for menu items, controls
- Tabs: Tabs are closed by default - call open_or_close_tab first
- Session State: Forms maintain state across tool calls within a session
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

import structlog

# Import MCP tool from Agent Framework
try:
    from agent_framework import MCPStreamableHTTPTool
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    MCPStreamableHTTPTool = None

# Import httpx for custom HTTP client
try:
    import httpx
    from httpx import AsyncClient, HTTPStatusError
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None
    AsyncClient = None
    HTTPStatusError = Exception

# Import observability
try:
    from src.observability import get_tracer, get_metrics
    OBSERVABILITY_AVAILABLE = True
except ImportError:
    OBSERVABILITY_AVAILABLE = False
    get_tracer = None
    get_metrics = None

# Import config model
try:
    from src.models.config import D365MCPConfig, D365OAuthConfig
    CONFIG_MODEL_AVAILABLE = True
except ImportError:
    CONFIG_MODEL_AVAILABLE = False
    D365MCPConfig = None
    D365OAuthConfig = None

if TYPE_CHECKING:
    from src.mcp.d365_oauth import D365TokenProvider
    from src.mcp.session import MCPSessionManager

logger = structlog.get_logger(__name__)


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""

    pass


class CircuitBreaker:
    """
    Simple circuit breaker for D365 MCP fault tolerance.

    States:
    - closed: Normal operation, requests pass through
    - open: Requests fail immediately (after failure_threshold failures)
    - half-open: Allow one test request after recovery_timeout

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)

        try:
            result = await breaker.call(async_function, *args, **kwargs)
        except CircuitBreakerOpen:
            # Handle circuit breaker open state
            pass
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        name: str = "d365",
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            name: Name for logging purposes
        """
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._name = name
        self._state = "closed"  # closed, open, half-open
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

        logger.debug(
            "CircuitBreaker initialized",
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitBreakerOpen: If circuit is open and recovery timeout not elapsed
            Exception: Any exception from func (also triggers circuit breaker)
        """
        async with self._lock:
            if self._state == "open":
                if time.time() - self._last_failure_time > self._recovery_timeout:
                    logger.info(
                        "Circuit breaker transitioning to half-open",
                        name=self._name,
                    )
                    self._state = "half-open"
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit breaker '{self._name}' is open. "
                        f"Retry after {self._recovery_timeout - (time.time() - self._last_failure_time):.1f}s"
                    )

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                self._failure_count = 0
                if self._state == "half-open":
                    logger.info(
                        "Circuit breaker transitioning to closed",
                        name=self._name,
                    )
                self._state = "closed"
            return result
        except Exception as e:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()
                if self._failure_count >= self._failure_threshold:
                    self._state = "open"
                    logger.error(
                        "Circuit breaker opened",
                        name=self._name,
                        failures=self._failure_count,
                        error=str(e),
                    )
            raise

    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._failure_count = 0
        self._state = "closed"
        self._last_failure_time = None
        logger.info("Circuit breaker reset", name=self._name)


class D365MCPTool:
    """
    D365 F&O MCP tool wrapper with production hardening.

    Wraps SDK's MCPStreamableHTTPTool with:
    - D365 OAuth token injection via custom HTTP client
    - Session context management for form state
    - Automatic token refresh handling with retry on 401
    - Circuit breaker for fault tolerance
    - OpenTelemetry tracing and metrics
    - Proper httpx timeout configuration

    Usage:
        from src.mcp.d365_tool import D365MCPTool
        from src.mcp.d365_oauth import D365TokenProvider
        from src.models.config import D365MCPConfig, D365OAuthConfig

        # Using config model (recommended)
        config = D365MCPConfig(
            name="d365-fo",
            oauth=D365OAuthConfig(
                environment_url="https://myorg.operations.dynamics.com",
                tenant_id="...",
                client_id="...",
                client_secret="...",
            ),
        )

        d365_tool = D365MCPTool(config=config)

        async with d365_tool:
            result = await d365_tool.call_tool("find_menu_item", {"search_string": "All customers"})
    """

    def __init__(
        self,
        config: Optional["D365MCPConfig"] = None,
        *,
        # Direct parameters (used if config not provided)
        name: str = "d365-fo",
        environment_url: Optional[str] = None,
        token_provider: Optional["D365TokenProvider"] = None,
        session_manager: Optional["MCPSessionManager"] = None,
        description: str = "D365 Finance & Operations MCP tools",
        timeout: float = 60.0,
        # Retry configuration
        max_retries: int = 3,
        retry_backoff_base: float = 1.0,
        retry_backoff_max: float = 30.0,
        # Circuit breaker configuration
        circuit_breaker_failure_threshold: int = 5,
        circuit_breaker_recovery_timeout: float = 30.0,
    ):
        """
        Initialize the D365 MCP tool.

        Args:
            config: D365MCPConfig instance (recommended)
            name: Name for this MCP tool instance
            environment_url: D365 F&O environment URL
            token_provider: D365TokenProvider instance for OAuth
            session_manager: Optional MCPSessionManager for form state tracking
            description: Tool description for agent introspection
            timeout: HTTP timeout in seconds (default: 60)
            max_retries: Maximum retry attempts (default: 3)
            retry_backoff_base: Exponential backoff base (default: 1.0)
            retry_backoff_max: Maximum backoff seconds (default: 30.0)
            circuit_breaker_failure_threshold: Failures before opening circuit (default: 5)
            circuit_breaker_recovery_timeout: Seconds before recovery attempt (default: 30.0)
        """
        if not MCP_AVAILABLE:
            raise ImportError(
                "agent-framework is required for D365 MCP. "
                "Install with: pip install agent-framework"
            )

        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for D365 MCP. "
                "Install with: pip install httpx"
            )

        # Use config model if provided
        if config is not None:
            self._config = config
            self.name = config.name
            self._environment_url = config.oauth.environment_url.rstrip("/")
            self._description = config.description
            self._max_retries = config.max_retries
            self._retry_backoff_base = config.retry_backoff_base
            self._retry_backoff_max = config.retry_backoff_max

            # Create token provider from config
            from src.mcp.d365_oauth import D365TokenProvider
            self._token_provider = D365TokenProvider(config=config.oauth)

            # Timeout configuration from config
            self._timeout_config = httpx.Timeout(
                connect=config.timeout_connect,
                read=config.timeout_read,
                write=config.timeout_write,
                pool=config.timeout_pool,
            )

            # Circuit breaker from config
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
                name=config.name,
            )
        else:
            self._config = None
            self.name = name
            if not environment_url:
                raise ValueError("environment_url is required when not using config")
            self._environment_url = environment_url.rstrip("/")
            self._description = description
            self._max_retries = max_retries
            self._retry_backoff_base = retry_backoff_base
            self._retry_backoff_max = retry_backoff_max

            # Token provider must be provided when not using config
            if not token_provider:
                raise ValueError("token_provider is required when not using config")
            self._token_provider = token_provider

            # Simple timeout (legacy mode)
            self._timeout_config = httpx.Timeout(timeout)

            # Circuit breaker
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=circuit_breaker_failure_threshold,
                recovery_timeout=circuit_breaker_recovery_timeout,
                name=name,
            )

        self._mcp_endpoint = f"{self._environment_url}/mcp"
        self._session_manager = session_manager

        self._mcp_tool: Optional[MCPStreamableHTTPTool] = None
        self._http_client: Optional[AsyncClient] = None
        self._connected = False

        # Observability (Phase 3)
        self._tracer = get_tracer() if OBSERVABILITY_AVAILABLE and get_tracer else None
        self._metrics = get_metrics() if OBSERVABILITY_AVAILABLE and get_metrics else None

        logger.debug(
            "D365MCPTool initialized",
            name=self.name,
            mcp_endpoint=self._mcp_endpoint,
            max_retries=self._max_retries,
        )

    async def connect(self) -> "MCPStreamableHTTPTool":
        """
        Connect to D365 MCP server with OAuth token.

        Creates an HTTP client with Bearer token authentication
        and initializes the MCPStreamableHTTPTool.

        Returns:
            Initialized MCPStreamableHTTPTool instance

        Raises:
            Exception: If connection fails
        """
        if self._connected and self._mcp_tool:
            logger.debug("Already connected to D365 MCP")
            return self._mcp_tool

        try:
            # Acquire OAuth token
            token = await self._token_provider.get_token()

            # Create HTTP client with Bearer token and proper timeout (Phase 3.2)
            self._http_client = AsyncClient(
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=self._timeout_config,
            )

            # Create MCPStreamableHTTPTool with custom HTTP client
            self._mcp_tool = MCPStreamableHTTPTool(
                name=self.name,
                url=self._mcp_endpoint,
                description=self._description,
                http_client=self._http_client,
            )

            # Enter the async context to initialize the tool
            await self._mcp_tool.__aenter__()
            self._connected = True

            logger.info(
                "Connected to D365 MCP",
                name=self.name,
                endpoint=self._mcp_endpoint,
                tool_count=len(self.tools) if hasattr(self._mcp_tool, "tools") else 0,
            )

            return self._mcp_tool

        except Exception as e:
            logger.error(
                "Failed to connect to D365 MCP",
                name=self.name,
                endpoint=self._mcp_endpoint,
                error=str(e),
            )
            await self._cleanup()
            raise

    async def refresh_token(self) -> None:
        """
        Refresh the OAuth token in the HTTP client.

        Call this periodically (before token expires) to maintain
        authenticated access to the D365 MCP server.
        """
        if not self._http_client:
            logger.warning("Cannot refresh token - no HTTP client")
            return

        try:
            token = await self._token_provider.refresh_token()
            self._http_client.headers["Authorization"] = f"Bearer {token}"
            logger.debug("Refreshed D365 OAuth token in HTTP client")
        except Exception as e:
            logger.error("Failed to refresh D365 token", error=str(e))
            raise

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Any:
        """
        Call a D365 MCP tool by name with retry and circuit breaker.

        Features:
        - Automatic retry on transient failures
        - Token refresh on 401 Unauthorized
        - Rate limit handling (429)
        - Circuit breaker for fault tolerance
        - OpenTelemetry tracing

        Args:
            tool_name: Name of the MCP tool to call
            arguments: Tool arguments
            chat_id: Optional chat ID for session management
            user_id: Optional user ID for session management

        Returns:
            Tool execution result

        Raises:
            RuntimeError: If not connected
            CircuitBreakerOpen: If circuit breaker is open
        """
        if not self._connected or not self._mcp_tool:
            raise RuntimeError("Not connected to D365 MCP. Call connect() first.")

        # Start tracing span (Phase 3.1)
        span = None
        if self._tracer:
            span = self._tracer.start_as_current_span(f"d365.{tool_name}")
            span.set_attribute("mcp.tool", tool_name)
            span.set_attribute("d365.environment", self._environment_url)

        start = time.perf_counter()

        try:
            # Execute with circuit breaker
            result = await self._circuit_breaker.call(
                self._execute_with_retry,
                tool_name,
                arguments,
                chat_id,
                user_id,
            )

            latency_ms = (time.perf_counter() - start) * 1000

            # Record metrics (Phase 3.1)
            if self._metrics:
                self._metrics.record_tool_call(
                    tool_name=f"d365.{tool_name}",
                    latency_ms=latency_ms,
                    success=True,
                )

            if span:
                span.set_attribute("success", True)
                span.set_attribute("latency_ms", latency_ms)

            return result

        except CircuitBreakerOpen:
            latency_ms = (time.perf_counter() - start) * 1000
            if self._metrics:
                self._metrics.record_tool_call(
                    tool_name=f"d365.{tool_name}",
                    latency_ms=latency_ms,
                    success=False,
                )
                self._metrics.record_error("CircuitBreakerOpen", "d365_mcp")
            if span:
                span.set_attribute("success", False)
                span.set_attribute("circuit_breaker", "open")
            raise

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000

            if self._metrics:
                self._metrics.record_tool_call(
                    tool_name=f"d365.{tool_name}",
                    latency_ms=latency_ms,
                    success=False,
                )
                self._metrics.record_error(type(e).__name__, "d365_mcp")

            if span:
                span.record_exception(e)
                span.set_attribute("success", False)

            raise

        finally:
            if span:
                span.end()

    async def _execute_with_retry(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        chat_id: Optional[str],
        user_id: Optional[str],
    ) -> Any:
        """
        Execute tool call with automatic retry and token refresh on 401.

        Args:
            tool_name: Name of the MCP tool to call
            arguments: Tool arguments
            chat_id: Optional chat ID for session management
            user_id: Optional user ID for session management

        Returns:
            Tool execution result
        """
        last_error = None

        for attempt in range(self._max_retries + 1):
            try:
                return await self._execute_tool_call(
                    tool_name, arguments, chat_id, user_id
                )

            except HTTPStatusError as e:
                if e.response.status_code == 401 and attempt < self._max_retries:
                    # Token expired - refresh and retry
                    logger.warning(
                        "Got 401, refreshing token",
                        attempt=attempt,
                        tool_name=tool_name,
                    )
                    await self.refresh_token()
                    continue

                elif e.response.status_code == 429:
                    # Rate limited - backoff
                    retry_after = int(e.response.headers.get("Retry-After", 5))
                    logger.warning(
                        "Rate limited, backing off",
                        attempt=attempt,
                        retry_after=retry_after,
                        tool_name=tool_name,
                    )
                    if attempt < self._max_retries:
                        await asyncio.sleep(retry_after)
                        continue

                # Other HTTP errors - don't retry
                raise

            except (ConnectionError, TimeoutError, OSError) as e:
                last_error = e
                if attempt < self._max_retries:
                    backoff = min(
                        self._retry_backoff_base * (2**attempt),
                        self._retry_backoff_max,
                    )
                    logger.warning(
                        "Transient error, retrying",
                        attempt=attempt,
                        backoff=backoff,
                        tool_name=tool_name,
                        error=str(e),
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise

        raise last_error or RuntimeError("Max retries exceeded")

    async def _execute_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        chat_id: Optional[str],
        user_id: Optional[str],
    ) -> Any:
        """
        Execute a single tool call (no retry).

        Args:
            tool_name: Name of the MCP tool to call
            arguments: Tool arguments
            chat_id: Optional chat ID for session management
            user_id: Optional user ID for session management

        Returns:
            Tool execution result
        """
        # Inject session context if session manager available
        if self._session_manager and chat_id:
            session = await self._session_manager.get_or_create_session(
                chat_id=chat_id,
                mcp_server_name=self.name,
                user_id=user_id,
            )
            session_kwargs = self._session_manager.build_mcp_kwargs(session)
            arguments = {**arguments, **session_kwargs}

        # Call the MCP tool
        result = await self._mcp_tool.call_tool(tool_name, arguments)

        # Process result for form context updates
        if self._session_manager and chat_id:
            await self._process_form_context(result, chat_id)

        return result

    async def _process_form_context(self, result: Any, chat_id: str) -> None:
        """
        Process tool result for D365 form context updates.

        Args:
            result: Tool execution result
            chat_id: Chat ID for session lookup
        """
        if not self._session_manager:
            return

        form_context = None
        form_name = None

        if isinstance(result, dict):
            form_context = result.get("form_context")
            form_name = result.get("form_name") or result.get("_form_name")
        elif hasattr(result, "form_context"):
            form_context = result.form_context
            form_name = getattr(result, "form_name", None)

        if form_context and form_name:
            session = await self._session_manager.get_or_create_session(
                chat_id=chat_id,
                mcp_server_name=self.name,
            )
            await self._session_manager.update_form_context(
                session_id=session.session_id,
                form_name=form_name,
                field_data=form_context if isinstance(form_context, dict) else {},
            )
            logger.debug(
                "Updated D365 form context",
                form_name=form_name,
                chat_id=chat_id,
            )

    async def _cleanup(self) -> None:
        """Clean up resources."""
        if self._mcp_tool:
            try:
                await self._mcp_tool.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error closing MCP tool", error=str(e))
            finally:
                self._mcp_tool = None

        if self._http_client:
            try:
                await self._http_client.aclose()
            except Exception as e:
                logger.warning("Error closing HTTP client", error=str(e))
            finally:
                self._http_client = None

        self._connected = False

    async def close(self) -> None:
        """
        Close all connections and release resources.

        Should be called when the tool is no longer needed.
        """
        await self._cleanup()
        await self._token_provider.close()
        logger.info("D365MCPTool closed", name=self.name)

    @asynccontextmanager
    async def session(self):
        """
        Context manager for D365 MCP tool lifecycle.

        Handles connection setup and teardown automatically.

        Usage:
            async with d365_tool.session() as mcp:
                result = await mcp.call_tool("find_menu_item", {"search_string": "..."})

        Yields:
            MCPStreamableHTTPTool instance
        """
        try:
            mcp_tool = await self.connect()
            yield mcp_tool
        finally:
            await self.close()

    @property
    def tools(self) -> List[Any]:
        """
        Get list of available MCP tools.

        Returns:
            List of tool definitions from the MCP server
        """
        if self._mcp_tool and hasattr(self._mcp_tool, "tools"):
            return self._mcp_tool.tools
        return []

    @property
    def is_connected(self) -> bool:
        """Check if connected to D365 MCP."""
        return self._connected

    @property
    def mcp_endpoint(self) -> str:
        """Get the MCP endpoint URL."""
        return self._mcp_endpoint

    @property
    def environment_url(self) -> str:
        """Get the D365 environment URL."""
        return self._environment_url

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Get the circuit breaker instance."""
        return self._circuit_breaker

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"D365MCPTool(name={self.name!r}, "
            f"endpoint={self._mcp_endpoint!r}, "
            f"connected={self._connected}, "
            f"circuit_state={self._circuit_breaker.state})"
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False
