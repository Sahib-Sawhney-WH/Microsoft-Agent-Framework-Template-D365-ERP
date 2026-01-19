"""Agent module - AI Assistant with dynamic tool loading and MCP support."""

from .assistant import AIAssistant, process_query
from .middleware import function_call_middleware

__all__ = [
    "AIAssistant",
    "process_query",
    "function_call_middleware",
]
