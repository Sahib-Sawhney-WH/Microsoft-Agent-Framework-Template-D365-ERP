"""
Example Tool package - demonstrates both SDK-compliant and legacy patterns.

Two tool patterns are available:

1. Decorator Pattern (SDK-compliant, recommended for new tools):
   from src.example_tool.tools import example_tool, example_echo

2. Service Pattern (Legacy, for enterprise config management):
   from src.example_tool.service import ExampleToolService
"""

# Decorator pattern (SDK-compliant, recommended)
from .tools import example_tool, example_echo

# Service pattern (legacy)
from .service import ExampleToolService, get_example_tool_service

__all__ = [
    # Decorator tools
    "example_tool",
    "example_echo",
    # Legacy service
    "ExampleToolService",
    "get_example_tool_service",
]
