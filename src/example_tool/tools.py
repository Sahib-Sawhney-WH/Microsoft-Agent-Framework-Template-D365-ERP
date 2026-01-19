"""
SDK-compliant example tool using decorator pattern.

This module demonstrates the recommended approach for creating tools
using @register_tool and Annotated type hints for automatic schema generation.

Usage:
    The tool is auto-discovered when enable_decorator_tools=True in config.
    It will be registered as "example_tool" and available to the LLM.

Example LLM interaction:
    User: "Use the example tool to say hello in uppercase"
    LLM: Calls example_tool(message="hello", uppercase=True)
    Result: "[Example Tool] Processed: HELLO"
"""

from typing import Annotated

from pydantic import Field

from src.loaders.decorators import register_tool

# Import ai_function from SDK (with fallback)
try:
    from semantic_kernel.functions import kernel_function as ai_function
except ImportError:
    try:
        from agents import function_tool as ai_function
    except ImportError:
        # Fallback: passthrough decorator when SDK not available
        def ai_function(func):
            """Passthrough decorator when SDK not available."""
            return func


@register_tool(name="example_tool", tags=["demo", "example"])
@ai_function
def example_tool(
    message: Annotated[str, Field(description="The message to process")],
    uppercase: Annotated[bool, Field(description="Convert output to uppercase")] = False,
) -> str:
    """
    An example tool demonstrating SDK-compliant patterns.

    This tool processes a message and optionally converts it to uppercase.
    Use this as a template for creating new decorator-based tools.
    """
    result = message.upper() if uppercase else message
    return f"[Example Tool] Processed: {result}"


@register_tool(name="example_echo", tags=["demo", "example"])
@ai_function
def example_echo(
    text: Annotated[str, Field(description="Text to echo back")],
    repeat: Annotated[int, Field(description="Number of times to repeat", ge=1, le=10)] = 1,
) -> str:
    """
    Echo text back a specified number of times.

    A simple demonstration tool that echoes the input text.
    Useful for testing tool invocation.
    """
    return " ".join([text] * repeat)
