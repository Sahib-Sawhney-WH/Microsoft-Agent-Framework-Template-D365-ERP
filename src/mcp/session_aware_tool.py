"""
Session-Aware MCP Tool Wrapper.

Wraps MCP tools to automatically inject session context for stateful
MCP servers like D365 ERP.

The wrapper intercepts tool invocations, retrieves or creates a session,
and injects session kwargs that the SDK passes through to the MCP server.
"""

from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.mcp.session import MCPSessionManager

logger = structlog.get_logger(__name__)


class SessionAwareMCPTool:
    """
    Wraps an MCP tool to inject session context via kwargs.

    This wrapper enables stateful MCP servers by:
    1. Intercepting tool invocations
    2. Getting or creating an MCP session
    3. Injecting session_id, user_id, and form_context into kwargs
    4. Passing the enhanced kwargs to the underlying tool
    5. Optionally updating session state based on response

    The SDK's kwargs pass-through mechanism ensures these values
    reach the MCP server, which can use them to maintain state.

    Usage:
        # Create the wrapper
        wrapped_tool = SessionAwareMCPTool(
            mcp_tool=original_tool,
            session_manager=session_manager,
            server_config={"name": "d365-erp", "stateful": True}
        )

        # Tool invocation now includes session context
        result = await wrapped_tool(query="Get sales order", chat_id="chat-123")
    """

    def __init__(
        self,
        mcp_tool: Any,
        session_manager: "MCPSessionManager",
        server_config: Dict[str, Any],
    ):
        """
        Initialize the session-aware tool wrapper.

        Args:
            mcp_tool: The underlying MCP tool to wrap
            session_manager: MCPSessionManager instance
            server_config: MCP server configuration dictionary containing:
                - name: Server name
                - stateful: Whether server requires sessions
                - session_header: Header name for session ID (optional)
                - form_context_header: Header name for form context (optional)
                - requires_user_id: Whether user_id is required (optional)
        """
        self._tool = mcp_tool
        self._session_manager = session_manager
        self._server_name = server_config.get("name", "unnamed-mcp")
        self._session_header = server_config.get("session_header", "X-Session-Id")
        self._form_context_header = server_config.get("form_context_header", "X-Form-Context")
        self._requires_session = server_config.get("stateful", False)
        self._requires_user_id = server_config.get("requires_user_id", False)

        # Copy tool metadata for agent introspection
        self._copy_tool_metadata()

        logger.debug(
            "Created SessionAwareMCPTool",
            server_name=self._server_name,
            requires_session=self._requires_session,
        )

    def _copy_tool_metadata(self) -> None:
        """Copy metadata from underlying tool for agent introspection."""
        # Copy common tool attributes that agents may inspect
        for attr in ["name", "description", "parameters", "schema", "__name__", "__doc__"]:
            if hasattr(self._tool, attr):
                try:
                    setattr(self, attr, getattr(self._tool, attr))
                except AttributeError:
                    pass  # Some attributes may be read-only

    async def __call__(self, **kwargs) -> Any:
        """
        Invoke the tool with session context injected.

        Session context is only injected if:
        1. The server is marked as stateful
        2. A chat_id is provided in kwargs

        Args:
            **kwargs: Tool invocation arguments, may include:
                - chat_id: Required for session management
                - user_id: Optional user identifier
                - Other tool-specific arguments

        Returns:
            Result from the underlying MCP tool
        """
        if self._requires_session:
            kwargs = await self._inject_session_context(kwargs)

        # Call underlying MCP tool
        result = await self._invoke_tool(**kwargs)

        # Process result for session updates
        if self._requires_session:
            await self._process_result(result, kwargs)

        return result

    async def _inject_session_context(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inject session context into kwargs.

        Args:
            kwargs: Original kwargs

        Returns:
            Enhanced kwargs with session context
        """
        chat_id = kwargs.get("chat_id")
        user_id = kwargs.get("user_id")

        if not chat_id:
            logger.debug("No chat_id provided, skipping session injection")
            return kwargs

        if self._requires_user_id and not user_id:
            logger.warning(
                "MCP server requires user_id but none provided",
                server_name=self._server_name,
            )

        try:
            # Get or create session
            session = await self._session_manager.get_or_create_session(
                chat_id=chat_id,
                mcp_server_name=self._server_name,
                user_id=user_id,
            )

            # Build and inject session kwargs
            session_kwargs = self._session_manager.build_mcp_kwargs(session)
            kwargs.update(session_kwargs)

            logger.debug(
                "Injected session context",
                session_id=session.session_id,
                server_name=self._server_name,
            )

        except Exception as e:
            logger.error(
                "Failed to inject session context",
                server_name=self._server_name,
                error=str(e),
            )

        return kwargs

    async def _invoke_tool(self, **kwargs) -> Any:
        """
        Invoke the underlying tool.

        Handles both callable tools and tools with invoke/run methods.

        Args:
            **kwargs: Tool arguments

        Returns:
            Tool result
        """
        # Filter out internal kwargs that shouldn't be passed to MCP
        internal_kwargs = {"chat_options", "tools", "chat_history"}
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in internal_kwargs}

        # Try different invocation patterns
        if callable(self._tool):
            return await self._tool(**filtered_kwargs)
        elif hasattr(self._tool, "invoke"):
            return await self._tool.invoke(**filtered_kwargs)
        elif hasattr(self._tool, "run"):
            return await self._tool.run(**filtered_kwargs)
        elif hasattr(self._tool, "__call__"):
            return await self._tool.__call__(**filtered_kwargs)
        else:
            raise TypeError(f"MCP tool {self._server_name} is not callable")

    async def _process_result(self, result: Any, kwargs: Dict[str, Any]) -> None:
        """
        Process tool result for session state updates.

        Checks if the result contains form_context updates
        and persists them to the session.

        Args:
            result: Result from the MCP tool
            kwargs: Original kwargs (contains session_id)
        """
        session_id = kwargs.get("session_id")
        if not session_id:
            return

        # Check for form context in result
        form_context = None
        form_name = None

        if isinstance(result, dict):
            form_context = result.get("form_context")
            form_name = result.get("form_name") or result.get("_form_name")
        elif hasattr(result, "form_context"):
            form_context = result.form_context
            form_name = getattr(result, "form_name", None)

        # Update session if form context returned
        if form_context and form_name:
            try:
                await self._session_manager.update_form_context(
                    session_id=session_id,
                    form_name=form_name,
                    field_data=form_context if isinstance(form_context, dict) else {},
                )
                logger.debug(
                    "Updated form context from result",
                    session_id=session_id,
                    form_name=form_name,
                )
            except Exception as e:
                logger.warning(
                    "Failed to update form context",
                    session_id=session_id,
                    error=str(e),
                )

    def __repr__(self) -> str:
        """String representation."""
        return f"SessionAwareMCPTool({self._server_name}, stateful={self._requires_session})"

    # Proxy common tool interface methods

    @property
    def tool_name(self) -> str:
        """Get the underlying tool name."""
        if hasattr(self._tool, "name"):
            return self._tool.name
        return self._server_name

    @property
    def is_stateful(self) -> bool:
        """Check if this tool requires session management."""
        return self._requires_session

    def get_schema(self) -> Optional[Dict[str, Any]]:
        """Get the tool schema if available."""
        if hasattr(self._tool, "schema"):
            return self._tool.schema
        if hasattr(self._tool, "get_schema"):
            return self._tool.get_schema()
        return None


def wrap_stateful_tools(
    tools: list[Any],
    session_manager: "MCPSessionManager",
    mcp_configs: list[Dict[str, Any]],
) -> list[Any]:
    """
    Wrap stateful MCP tools with session awareness.

    Utility function to wrap multiple tools based on their configuration.

    Args:
        tools: List of MCP tool instances
        session_manager: MCPSessionManager instance
        mcp_configs: List of MCP server configurations

    Returns:
        List of tools, with stateful ones wrapped
    """
    # Build lookup of stateful servers
    stateful_servers: Dict[str, Dict[str, Any]] = {}
    for config in mcp_configs:
        if config.get("stateful", False):
            name = config.get("name", "")
            stateful_servers[name] = config

    # Wrap stateful tools
    wrapped_tools = []
    for tool in tools:
        tool_name = getattr(tool, "name", str(tool))

        if tool_name in stateful_servers:
            wrapped_tool = SessionAwareMCPTool(
                mcp_tool=tool,
                session_manager=session_manager,
                server_config=stateful_servers[tool_name],
            )
            wrapped_tools.append(wrapped_tool)
            logger.debug("Wrapped stateful tool", tool_name=tool_name)
        else:
            wrapped_tools.append(tool)

    stateful_count = len(stateful_servers)
    logger.info(
        "Processed MCP tools for session awareness",
        total_tools=len(tools),
        stateful_tools=stateful_count,
    )

    return wrapped_tools
