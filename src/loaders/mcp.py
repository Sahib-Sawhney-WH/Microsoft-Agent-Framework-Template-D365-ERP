"""
MCP (Model Context Protocol) loader for the AI Assistant.

Loads and manages MCP server connections from configuration.
Supports MCP transport types:
- stdio: Local process-based MCP servers
- http: HTTP/SSE MCP servers
- websocket: WebSocket MCP servers
- d365: D365 Finance & Operations with OAuth authentication
"""

from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from contextlib import AsyncExitStack

import structlog

# Import MCP tool types from Agent Framework
try:
    from agent_framework import MCPStdioTool, MCPStreamableHTTPTool, MCPWebsocketTool
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    MCPStdioTool = None
    MCPStreamableHTTPTool = None
    MCPWebsocketTool = None

# Import D365 MCP components
try:
    from src.mcp.d365_oauth import D365TokenProvider
    from src.mcp.d365_tool import D365MCPTool
    D365_MCP_AVAILABLE = True
except ImportError:
    D365_MCP_AVAILABLE = False
    D365TokenProvider = None
    D365MCPTool = None

# Import D365 config models
try:
    from src.models.config import D365MCPConfig, D365OAuthConfig
    D365_CONFIG_AVAILABLE = True
except ImportError:
    D365_CONFIG_AVAILABLE = False
    D365MCPConfig = None
    D365OAuthConfig = None

if TYPE_CHECKING:
    from src.mcp.session import MCPSessionManager

logger = structlog.get_logger(__name__)


class MCPManager:
    """
    Manages MCP server connections for the AI Assistant.
    
    Loads MCP configurations and creates appropriate tool instances
    based on transport type (stdio, http, websocket).
    
    Enhanced with session management support for stateful MCP servers
    like D365 ERP that require session continuity.
    """
    
    def __init__(self):
        """Initialize the MCP manager."""
        self._exit_stack: Optional[AsyncExitStack] = None
        self._mcp_tools: List[Any] = []
        self._mcp_configs: List[Dict[str, Any]] = []
        self._session_manager: Optional["MCPSessionManager"] = None
        self._stateful_servers: Set[str] = set()
        self._initialized = False

    def set_session_manager(self, manager: "MCPSessionManager") -> None:
        """
        Attach session manager for stateful MCP servers.
        
        When a session manager is attached, stateful MCP tools will be
        wrapped to automatically inject session context.
        
        Args:
            manager: MCPSessionManager instance
        """
        self._session_manager = manager
        
        # Re-wrap tools if already loaded
        if self._initialized and self._mcp_tools:
            self._wrap_stateful_tools()
            logger.info(
                "Session manager attached to MCP manager",
                stateful_servers=list(self._stateful_servers)
            )
        
    async def load_mcp_servers(self, mcp_configs: List[Dict[str, Any]]) -> List[Any]:
        """
        Load and initialize MCP servers from configuration.
        
        Args:
            mcp_configs: List of MCP server configurations, each containing:
                - name: Friendly name for the MCP server
                - type: "stdio", "http", or "websocket"
                - enabled: Whether this MCP is enabled (default: true)
                - stateful: Whether this server requires session management (default: false)
                - session_header: Header name for session ID (for stateful servers)
                - form_context_header: Header name for form context (for D365)
                - requires_user_id: Whether user_id is required (for stateful servers)
                
                For stdio type:
                - command: Command to run (e.g., "uvx", "npx")
                - args: List of arguments
                - env: Optional environment variables dict
                
                For http type:
                - url: HTTP URL of the MCP server
                - headers: Optional headers dict (for auth, etc.)
                
                For websocket type:
                - url: WebSocket URL (wss://...)
                - headers: Optional headers dict (for auth, etc.)
                
        Returns:
            List of initialized MCP tool instances
        """
        if not MCP_AVAILABLE:
            logger.warning(
                "MCP tools not available. Install agent-framework with MCP support."
            )
            return []
        
        if not mcp_configs:
            logger.debug("No MCP servers configured")
            return []
        
        # Store configs for later session wrapping
        self._mcp_configs = mcp_configs
        
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        
        for config in mcp_configs:
            # Skip disabled MCPs
            if not config.get("enabled", True):
                logger.debug("Skipping disabled MCP", name=config.get("name"))
                continue
            
            # Track stateful servers
            if config.get("stateful", False):
                self._stateful_servers.add(config.get("name", ""))
                
            try:
                mcp_tool = await self._create_mcp_tool(config)
                if mcp_tool:
                    self._mcp_tools.append(mcp_tool)
                    logger.info(
                        "Loaded MCP server",
                        name=config.get("name"),
                        type=config.get("type"),
                        stateful=config.get("stateful", False)
                    )
            except Exception as e:
                logger.error(
                    "Failed to load MCP server",
                    name=config.get("name"),
                    error=str(e)
                )
        
        self._initialized = True
        
        # Wrap stateful tools if session manager is available
        if self._session_manager and self._stateful_servers:
            self._wrap_stateful_tools()
        
        logger.info(
            "MCP servers loaded",
            count=len(self._mcp_tools),
            stateful_count=len(self._stateful_servers)
        )
        return self._mcp_tools

    def _wrap_stateful_tools(self) -> None:
        """Wrap stateful MCP tools with session awareness."""
        if not self._session_manager:
            return
        
        from src.mcp.session_aware_tool import SessionAwareMCPTool
        
        # Build config lookup for stateful servers
        stateful_configs: Dict[str, Dict[str, Any]] = {}
        for config in self._mcp_configs:
            if config.get("stateful", False):
                stateful_configs[config.get("name", "")] = config
        
        # Wrap the tools
        wrapped_tools = []
        for tool in self._mcp_tools:
            tool_name = getattr(tool, "name", str(tool))
            
            if tool_name in stateful_configs:
                wrapped_tool = SessionAwareMCPTool(
                    mcp_tool=tool,
                    session_manager=self._session_manager,
                    server_config=stateful_configs[tool_name],
                )
                wrapped_tools.append(wrapped_tool)
                logger.debug("Wrapped stateful MCP tool", tool_name=tool_name)
            else:
                wrapped_tools.append(tool)
        
        self._mcp_tools = wrapped_tools
        logger.info("Wrapped stateful MCP tools", count=len(stateful_configs))
    
    async def _create_mcp_tool(self, config: Dict[str, Any]) -> Optional[Any]:
        """Create an MCP tool instance based on configuration."""
        mcp_type = config.get("type", "").lower()
        name = config.get("name", "unnamed-mcp")

        if mcp_type == "stdio":
            return await self._create_stdio_mcp(config)
        elif mcp_type == "http":
            return await self._create_http_mcp(config)
        elif mcp_type == "websocket":
            return await self._create_websocket_mcp(config)
        elif mcp_type == "d365":
            return await self._create_d365_mcp(config)
        else:
            logger.error("Unknown MCP type", name=name, type=mcp_type)
            return None
    
    async def _create_stdio_mcp(self, config: Dict[str, Any]) -> Any:
        """Create a stdio-based MCP tool."""
        command = config.get("command")
        if not command:
            raise ValueError(f"MCP '{config.get('name')}' requires 'command' for stdio type")
        
        mcp_tool = MCPStdioTool(
            name=config.get("name", "stdio-mcp"),
            command=command,
            args=config.get("args", []),
            env=config.get("env"),
        )
        
        # Enter the async context to initialize the MCP
        initialized_tool = await self._exit_stack.enter_async_context(mcp_tool)
        return initialized_tool
    
    async def _create_http_mcp(self, config: Dict[str, Any]) -> Any:
        """Create an HTTP-based MCP tool."""
        url = config.get("url")
        if not url:
            raise ValueError(f"MCP '{config.get('name')}' requires 'url' for http type")
        
        mcp_tool = MCPStreamableHTTPTool(
            name=config.get("name", "http-mcp"),
            url=url,
            headers=config.get("headers", {}),
        )
        
        initialized_tool = await self._exit_stack.enter_async_context(mcp_tool)
        return initialized_tool
    
    async def _create_websocket_mcp(self, config: Dict[str, Any]) -> Any:
        """Create a WebSocket-based MCP tool."""
        url = config.get("url")
        if not url:
            raise ValueError(f"MCP '{config.get('name')}' requires 'url' for websocket type")

        mcp_tool = MCPWebsocketTool(
            name=config.get("name", "websocket-mcp"),
            url=url,
            headers=config.get("headers", {}),
        )

        initialized_tool = await self._exit_stack.enter_async_context(mcp_tool)
        return initialized_tool

    async def _create_d365_mcp(self, config: Dict[str, Any]) -> Any:
        """
        Create a D365 Finance & Operations MCP tool with OAuth.

        D365 MCP uses Azure AD OAuth for authentication. The tool handles
        token acquisition and refresh automatically.

        D365 MCP is inherently stateful - it maintains form state across
        tool calls within a session. This method automatically:
        1. Marks the server as stateful for session tracking
        2. Injects the session manager for form context management

        Production hardening features (via D365MCPConfig):
        - Retry logic with exponential backoff
        - Circuit breaker for fault tolerance
        - Proper httpx timeout configuration
        - OpenTelemetry observability

        Config format (dict-based, legacy):
            [[agent.mcp]]
            name = "d365-fo"
            type = "d365"
            enabled = true
            description = "D365 Finance & Operations"

            [agent.mcp.oauth]
            environment_url = "https://myorg.operations.dynamics.com"
            tenant_id = "your-tenant-id"        # Optional
            client_id = "your-client-id"        # Optional
            client_secret = "${D365_CLIENT_SECRET}"  # Optional, use env var

        Config format (with production hardening):
            [[agent.mcp]]
            name = "d365-fo"
            type = "d365"
            enabled = true
            description = "D365 Finance & Operations"
            max_retries = 3
            timeout_connect = 10.0
            timeout_read = 60.0
            timeout_write = 10.0
            circuit_breaker_failure_threshold = 5
            circuit_breaker_recovery_timeout = 30.0

            [agent.mcp.oauth]
            environment_url = "https://myorg.operations.dynamics.com"
            tenant_id = "your-tenant-id"
            client_id = "your-client-id"
            client_secret = "${D365_CLIENT_SECRET}"

        Args:
            config: MCP configuration dictionary

        Returns:
            D365MCPTool instance

        Raises:
            ImportError: If D365 MCP components not available
            ValueError: If required oauth config is missing
        """
        if not D365_MCP_AVAILABLE:
            raise ImportError(
                "D365 MCP components not available. "
                "Ensure azure-identity and httpx are installed."
            )

        name = config.get("name", "d365-fo")

        # D365 MCP is always stateful - mark it for session tracking
        # This ensures proper form context management across tool calls
        config["stateful"] = True
        config.setdefault("session_header", "X-D365-Session-Id")
        config.setdefault("form_context_header", "X-D365-Form-Context")

        # Extract OAuth configuration
        oauth_config = config.get("oauth", {})
        environment_url = oauth_config.get("environment_url")

        if not environment_url:
            raise ValueError(
                f"MCP '{name}' requires 'oauth.environment_url' for d365 type"
            )

        # Try to use Pydantic config models for production hardening
        if D365_CONFIG_AVAILABLE:
            try:
                # Build D365MCPConfig from dict config
                d365_config = D365MCPConfig(
                    name=name,
                    enabled=config.get("enabled", True),
                    description=config.get("description", "D365 Finance & Operations"),
                    oauth=D365OAuthConfig(
                        environment_url=environment_url,
                        tenant_id=oauth_config.get("tenant_id"),
                        client_id=oauth_config.get("client_id"),
                        client_secret=oauth_config.get("client_secret"),
                        token_refresh_buffer_minutes=oauth_config.get(
                            "token_refresh_buffer_minutes", 5
                        ),
                    ),
                    timeout_connect=config.get("timeout_connect", 10.0),
                    timeout_read=config.get("timeout_read", 60.0),
                    timeout_write=config.get("timeout_write", 10.0),
                    timeout_pool=config.get("timeout_pool", 5.0),
                    max_retries=config.get("max_retries", 3),
                    retry_backoff_base=config.get("retry_backoff_base", 1.0),
                    retry_backoff_max=config.get("retry_backoff_max", 30.0),
                    health_check_enabled=config.get("health_check_enabled", True),
                    health_check_interval=config.get("health_check_interval", 60),
                    circuit_breaker_failure_threshold=config.get(
                        "circuit_breaker_failure_threshold", 5
                    ),
                    circuit_breaker_recovery_timeout=config.get(
                        "circuit_breaker_recovery_timeout", 30.0
                    ),
                )

                # Create D365 MCP tool with config model (production hardened)
                d365_tool = D365MCPTool(config=d365_config)

                # Inject session manager if available
                d365_tool._session_manager = self._session_manager

                logger.info(
                    "Creating D365 MCP tool with production hardening",
                    name=name,
                    max_retries=d365_config.max_retries,
                    circuit_breaker_threshold=d365_config.circuit_breaker_failure_threshold,
                )

            except Exception as e:
                logger.warning(
                    "Failed to create D365 MCP with config model, falling back to legacy",
                    error=str(e),
                )
                # Fall through to legacy creation
                d365_tool = None

            if d365_tool:
                # Connect and enter async context
                await d365_tool.connect()

                # Register cleanup with exit stack
                self._exit_stack.push_async_callback(d365_tool.close)

                logger.info(
                    "Created D365 MCP tool (production hardened)",
                    name=name,
                    environment_url=environment_url,
                    tool_count=len(d365_tool.tools),
                )

                return d365_tool

        # Legacy creation (backward compatible)
        # Create token provider
        token_provider = D365TokenProvider(
            environment_url=environment_url,
            tenant_id=oauth_config.get("tenant_id"),
            client_id=oauth_config.get("client_id"),
            client_secret=oauth_config.get("client_secret"),
        )

        # Create D365 MCP tool with session manager for form state tracking
        d365_tool = D365MCPTool(
            name=name,
            environment_url=environment_url,
            token_provider=token_provider,
            session_manager=self._session_manager,
            description=config.get("description", "D365 Finance & Operations MCP"),
            timeout=config.get("timeout", 60.0),
            max_retries=config.get("max_retries", 3),
            retry_backoff_base=config.get("retry_backoff_base", 1.0),
            retry_backoff_max=config.get("retry_backoff_max", 30.0),
            circuit_breaker_failure_threshold=config.get(
                "circuit_breaker_failure_threshold", 5
            ),
            circuit_breaker_recovery_timeout=config.get(
                "circuit_breaker_recovery_timeout", 30.0
            ),
        )

        # Connect and enter async context
        await d365_tool.connect()

        # Register cleanup with exit stack
        self._exit_stack.push_async_callback(d365_tool.close)

        # Note: D365MCPTool handles session management internally via its
        # session_manager parameter. We do NOT add it to _stateful_servers
        # to avoid double-wrapping with SessionAwareMCPTool.
        # The config["stateful"] = True is set for metadata/logging purposes.

        logger.info(
            "Created D365 MCP tool (stateful, internal session management)",
            name=name,
            environment_url=environment_url,
            tool_count=len(d365_tool.tools),
        )

        return d365_tool

    @property
    def tools(self) -> List[Any]:
        """Get list of loaded MCP tools."""
        return self._mcp_tools
    
    async def close(self) -> None:
        """Close all MCP connections."""
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
                logger.info("Closed all MCP connections")
            except Exception as e:
                logger.error("Error closing MCP connections", error=str(e))
            finally:
                self._exit_stack = None
                self._mcp_tools = []
                self._initialized = False


def parse_mcp_configs(config_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse MCP configurations from agent config.
    
    Supports two formats in TOML:
    
    1. Array format (recommended for multiple MCPs):
        [[agent.mcp]]
        name = "calculator"
        type = "stdio"
        command = "uvx"
        args = ["mcp-server-calculator"]
        
        [[agent.mcp]]
        name = "docs"
        type = "http"
        url = "https://api.example.com/mcp"
    
    2. Table format (for single MCP or named MCPs):
        [agent.mcp.calculator]
        type = "stdio"
        command = "uvx"
        args = ["mcp-server-calculator"]
    
    Args:
        config_dict: The agent configuration dictionary
        
    Returns:
        List of MCP configuration dictionaries
    """
    mcp_config = config_dict.get("mcp", {})
    
    # If it's a list, return as-is
    if isinstance(mcp_config, list):
        return mcp_config
    
    # If it's a dict, convert to list format
    if isinstance(mcp_config, dict):
        mcp_list = []
        for name, settings in mcp_config.items():
            if isinstance(settings, dict):
                # Add name from key if not specified
                if "name" not in settings:
                    settings["name"] = name
                mcp_list.append(settings)
        return mcp_list
    
    return []
