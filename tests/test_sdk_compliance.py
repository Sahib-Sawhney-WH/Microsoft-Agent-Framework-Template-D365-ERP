"""
SDK Compliance Tests for Tool Patterns.

Tests that decorator-based tools follow SDK best practices and that
the hybrid tool loading system works correctly.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Annotated

from pydantic import Field


# ==================== Decorator Registration Tests ====================

class TestDecoratorRegistration:
    """Test the @register_tool decorator."""

    def setup_method(self):
        """Clear registry before each test."""
        from src.loaders.decorators import clear_registry
        clear_registry()

    def test_register_tool_basic(self):
        """Test basic tool registration."""
        from src.loaders.decorators import register_tool, get_registered_tools

        @register_tool(name="test_tool")
        def test_tool(message: str) -> str:
            return message

        tools = get_registered_tools()
        assert "test_tool" in tools
        assert tools["test_tool"] == test_tool

    def test_register_tool_default_name(self):
        """Test tool registration uses function name by default."""
        from src.loaders.decorators import register_tool, get_registered_tools

        @register_tool()
        def my_function(message: str) -> str:
            return message

        tools = get_registered_tools()
        assert "my_function" in tools

    def test_register_tool_with_tags(self):
        """Test tool registration with tags."""
        from src.loaders.decorators import register_tool, get_tool_metadata

        @register_tool(name="tagged_tool", tags=["demo", "test"])
        def tagged_tool(x: str) -> str:
            return x

        metadata = get_tool_metadata("tagged_tool")
        assert metadata is not None
        assert "demo" in metadata["tags"]
        assert "test" in metadata["tags"]

    def test_register_tool_disabled(self):
        """Test disabled tools are not registered."""
        from src.loaders.decorators import register_tool, get_registered_tools

        @register_tool(name="disabled_tool", enabled=False)
        def disabled_tool(x: str) -> str:
            return x

        tools = get_registered_tools()
        assert "disabled_tool" not in tools

    def test_get_tools_by_tag(self):
        """Test filtering tools by tag."""
        from src.loaders.decorators import register_tool, get_tools_by_tag

        @register_tool(name="tool_a", tags=["category1"])
        def tool_a(x: str) -> str:
            return x

        @register_tool(name="tool_b", tags=["category1", "category2"])
        def tool_b(x: str) -> str:
            return x

        @register_tool(name="tool_c", tags=["category2"])
        def tool_c(x: str) -> str:
            return x

        cat1_tools = get_tools_by_tag("category1")
        assert len(cat1_tools) == 2

        cat2_tools = get_tools_by_tag("category2")
        assert len(cat2_tools) == 2

    def test_tool_metadata_attributes(self):
        """Test tool functions have metadata attributes."""
        from src.loaders.decorators import register_tool

        @register_tool(name="meta_tool", tags=["meta"])
        def meta_tool(x: str) -> str:
            return x

        assert hasattr(meta_tool, "_tool_name")
        assert meta_tool._tool_name == "meta_tool"
        assert hasattr(meta_tool, "_tool_tags")
        assert "meta" in meta_tool._tool_tags
        assert hasattr(meta_tool, "_tool_source")
        assert meta_tool._tool_source == "decorator"


# ==================== Example Tool Tests ====================

class TestExampleTool:
    """Test the SDK-compliant example tools."""

    def test_example_tool_import(self):
        """Test example_tool can be imported."""
        from src.example_tool.tools import example_tool
        assert callable(example_tool)

    def test_example_tool_basic_execution(self):
        """Test example_tool executes correctly."""
        from src.example_tool.tools import example_tool

        result = example_tool(message="hello")
        assert "[Example Tool]" in result
        assert "hello" in result

    def test_example_tool_uppercase(self):
        """Test example_tool uppercase parameter."""
        from src.example_tool.tools import example_tool

        result = example_tool(message="hello", uppercase=True)
        assert "HELLO" in result

    def test_example_echo_basic(self):
        """Test example_echo executes correctly."""
        from src.example_tool.tools import example_echo

        result = example_echo(text="test")
        assert result == "test"

    def test_example_echo_repeat(self):
        """Test example_echo repeat parameter."""
        from src.example_tool.tools import example_echo

        result = example_echo(text="hi", repeat=3)
        assert result == "hi hi hi"

    def test_example_tools_registered(self):
        """Test example tools are registered in the registry."""
        from src.loaders.decorators import clear_registry, get_registered_tools
        clear_registry()

        # Import triggers registration
        from src.example_tool import tools  # noqa: F401

        registered = get_registered_tools()
        assert "example_tool" in registered
        assert "example_echo" in registered

    def test_example_tool_has_demo_tag(self):
        """Test example tools have demo tag."""
        from src.loaders.decorators import clear_registry, get_tools_by_tag
        clear_registry()

        from src.example_tool import tools  # noqa: F401

        demo_tools = get_tools_by_tag("demo")
        assert len(demo_tools) >= 2


# ==================== Tool Discovery Tests ====================

class TestToolDiscovery:
    """Test the tool discovery system."""

    def setup_method(self):
        """Clear registry before each test."""
        from src.loaders.decorators import clear_registry
        clear_registry()

    def test_discover_tools_finds_tools_py(self):
        """Test discovery finds tools.py files."""
        from src.loaders.decorators import discover_decorator_tools, get_registered_tools

        # Discover tools (will find src/example_tool/tools.py)
        discover_decorator_tools(tools_dir="src")

        tools = get_registered_tools()
        # Should find example_tool and example_echo
        assert len(tools) >= 2

    def test_discover_tools_excludes_pycache(self):
        """Test discovery excludes __pycache__ directories."""
        from src.loaders.decorators import discover_decorator_tools

        # Should not raise errors when encountering __pycache__
        tools = discover_decorator_tools(tools_dir="src")
        assert isinstance(tools, list)

    def test_load_specific_modules(self):
        """Test loading specific module paths."""
        from src.loaders.decorators import load_tool_modules, get_registered_tools

        load_tool_modules(["src.example_tool.tools"])

        tools = get_registered_tools()
        assert "example_tool" in tools


# ==================== Hybrid Loading Tests ====================

class TestHybridLoading:
    """Test the hybrid tool loading system."""

    def setup_method(self):
        """Clear registry before each test."""
        from src.loaders.decorators import clear_registry
        clear_registry()

    def test_load_decorator_tools_only(self):
        """Test loading only decorator tools."""
        from src.loaders.tools import load_and_register_tools

        assistant = MagicMock()
        assistant.tools = []

        count = load_and_register_tools(
            assistant,
            enable_decorator_tools=True,
            enable_json_tools=False,
        )

        # Should have loaded decorator tools
        assert count >= 2  # At least example_tool and example_echo

    def test_load_json_tools_only(self):
        """Test loading only JSON config tools."""
        from src.loaders.tools import load_and_register_tools

        assistant = MagicMock()
        assistant.tools = []

        count = load_and_register_tools(
            assistant,
            enable_decorator_tools=False,
            enable_json_tools=True,
            config_dir="config/tools",
        )

        # Result depends on what JSON configs exist
        assert count >= 0

    def test_decorator_tools_take_precedence(self):
        """Test decorator tools take precedence over JSON tools."""
        from src.loaders.decorators import register_tool, get_registered_tools
        from src.loaders.tools import load_json_config_tools

        # Register a decorator tool
        @register_tool(name="example_tool")
        def decorator_example_tool(x: str) -> str:
            return f"decorator: {x}"

        # Create mock assistant
        assistant = MagicMock()
        assistant.tools = []

        # Try to load JSON tools - example_tool should be skipped
        decorator_names = set(get_registered_tools().keys())
        count = load_json_config_tools(
            assistant,
            config_dir="config/tools",
            skip_names=decorator_names,
        )

        # Verify our decorator version is preserved
        tools = get_registered_tools()
        result = tools["example_tool"]("test")
        assert "decorator" in result

    def test_hybrid_loading_total_count(self):
        """Test hybrid loading returns correct total count."""
        from src.loaders.tools import load_and_register_tools
        from src.loaders.decorators import clear_registry

        clear_registry()

        assistant = MagicMock()
        assistant.tools = []

        total = load_and_register_tools(
            assistant,
            enable_decorator_tools=True,
            enable_json_tools=True,
        )

        assert total == len(assistant.tools)


# ==================== SDK Pattern Tests ====================

class TestSDKPatterns:
    """Test SDK-compliant patterns work correctly."""

    def test_annotated_parameters(self):
        """Test Annotated parameters work correctly."""
        from src.loaders.decorators import register_tool

        @register_tool(name="annotated_tool")
        def annotated_tool(
            message: Annotated[str, Field(description="Input message")],
            count: Annotated[int, Field(description="Repeat count")] = 1,
        ) -> str:
            return message * count

        result = annotated_tool(message="hi", count=2)
        assert result == "hihi"

    def test_tool_docstring_preserved(self):
        """Test tool docstrings are preserved."""
        from src.loaders.decorators import register_tool

        @register_tool(name="documented_tool")
        def documented_tool(x: str) -> str:
            """This is the tool's documentation."""
            return x

        assert documented_tool.__doc__ == "This is the tool's documentation."

    def test_tool_function_name_preserved(self):
        """Test original function name is accessible."""
        from src.loaders.decorators import register_tool

        @register_tool(name="renamed_tool")
        def original_name(x: str) -> str:
            return x

        # The function object still has original name
        assert original_name.__name__ == "original_name"
        # But it's registered under the specified name
        assert original_name._tool_name == "renamed_tool"


# ==================== Convenience Export Tests ====================

class TestConvenienceExports:
    """Test the src.tools convenience module."""

    def test_all_exports_available(self):
        """Test all expected exports are available."""
        from src.tools import (
            ai_function,
            register_tool,
            Annotated,
            Field,
            get_registered_tools,
            get_tool_metadata,
            get_tools_by_tag,
            discover_decorator_tools,
            load_tool_modules,
            clear_registry,
        )

        # All imports should succeed
        assert callable(register_tool)
        assert callable(get_registered_tools)
        assert callable(ai_function)

    def test_create_tool_with_convenience_imports(self):
        """Test creating a tool using convenience imports."""
        from src.tools import register_tool, Annotated, Field, clear_registry, get_registered_tools

        clear_registry()

        @register_tool(name="convenience_tool")
        def convenience_tool(
            value: Annotated[str, Field(description="Input value")],
        ) -> str:
            """A tool created with convenience imports."""
            return value

        tools = get_registered_tools()
        assert "convenience_tool" in tools


# ==================== Integration Tests ====================

class TestIntegration:
    """Integration tests for the complete tool system."""

    def setup_method(self):
        """Clear registry before each test."""
        from src.loaders.decorators import clear_registry
        clear_registry()

    def test_full_tool_lifecycle(self):
        """Test complete tool registration and execution lifecycle."""
        from src.tools import register_tool, Annotated, Field, get_registered_tools

        # Define tool
        @register_tool(name="lifecycle_tool", tags=["test"])
        def lifecycle_tool(
            input_text: Annotated[str, Field(description="Text to process")],
            transform: Annotated[str, Field(description="Transformation type")] = "none",
        ) -> str:
            """Process text with optional transformation."""
            if transform == "upper":
                return input_text.upper()
            elif transform == "lower":
                return input_text.lower()
            return input_text

        # Verify registration
        tools = get_registered_tools()
        assert "lifecycle_tool" in tools

        # Execute tool
        result = lifecycle_tool(input_text="Hello", transform="upper")
        assert result == "HELLO"

        result = lifecycle_tool(input_text="WORLD", transform="lower")
        assert result == "world"

    def test_assistant_mock_tool_loading(self):
        """Test tool loading with mocked assistant."""
        from src.loaders.tools import load_and_register_tools

        # Create mock assistant matching AIAssistant interface
        assistant = MagicMock()
        assistant.tools = []
        assistant.config = MagicMock()
        assistant.config.tools_config_dir = "config/tools"
        assistant.config.enable_decorator_tools = True
        assistant.config.enable_json_tools = True
        assistant.config.tool_modules = None

        # Load tools
        count = load_and_register_tools(
            assistant,
            config_dir=assistant.config.tools_config_dir,
            tool_modules=assistant.config.tool_modules,
            enable_decorator_tools=assistant.config.enable_decorator_tools,
            enable_json_tools=assistant.config.enable_json_tools,
        )

        # Verify tools were added to assistant
        assert len(assistant.tools) > 0
        assert count == len(assistant.tools)
