"""
MCP (Model Context Protocol) session management package.

Provides session handling for stateful MCP servers like D365 ERP
that require session continuity across tool invocations.

Includes D365 Finance & Operations integration with Azure AD OAuth.
"""

from src.mcp.session import (
    MCPSessionState,
    MCPSessionManager,
    MCPSessionConfig,
    parse_mcp_session_config,
)
from src.mcp.session_aware_tool import SessionAwareMCPTool, wrap_stateful_tools

# D365 F&O components (optional - require azure-identity)
try:
    from src.mcp.d365_oauth import D365TokenProvider
    from src.mcp.d365_tool import D365MCPTool
    _D365_AVAILABLE = True
except ImportError:
    D365TokenProvider = None
    D365MCPTool = None
    _D365_AVAILABLE = False

__all__ = [
    # Session management
    "MCPSessionState",
    "MCPSessionManager",
    "MCPSessionConfig",
    "SessionAwareMCPTool",
    "parse_mcp_session_config",
    "wrap_stateful_tools",
    # D365 F&O (optional)
    "D365TokenProvider",
    "D365MCPTool",
]
