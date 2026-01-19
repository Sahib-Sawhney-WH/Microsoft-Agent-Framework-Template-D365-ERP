"""
Convenience exports for SDK-compliant tool development.

This module provides all the imports needed for creating decorator-based
tools following SDK best practices with @ai_function and Annotated types.

Usage:
    from src.tools import ai_function, register_tool, Annotated, Field

    @register_tool(tags=["demo"])
    @ai_function
    def my_tool(
        message: Annotated[str, Field(description="Input message")],
        uppercase: Annotated[bool, Field(description="Convert to uppercase")] = False,
    ) -> str:
        '''Tool docstring becomes AI's understanding.'''
        return message.upper() if uppercase else message

For more details, see docs/tools.md
"""

from typing import Annotated

from pydantic import Field

# SDK ai_function decorator (when available)
try:
    from semantic_kernel.functions import kernel_function as ai_function
except ImportError:
    try:
        from agents import function_tool as ai_function
    except ImportError:
        # Fallback: create a passthrough decorator
        def ai_function(func):
            """Passthrough decorator when SDK not available."""
            return func

# Local registration system
from src.loaders.decorators import (
    register_tool,
    get_registered_tools,
    get_tool_metadata,
    get_tools_by_tag,
    discover_decorator_tools,
    load_tool_modules,
    clear_registry,
)

__all__ = [
    # SDK Patterns
    "ai_function",
    "Annotated",
    "Field",
    # Registration System
    "register_tool",
    "get_registered_tools",
    "get_tool_metadata",
    "get_tools_by_tag",
    "discover_decorator_tools",
    "load_tool_modules",
    "clear_registry",
]
