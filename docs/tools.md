# Tool Development Guide

This guide covers how to create tools for the Microsoft Agent Framework. The framework supports two patterns for defining tools:

1. **Decorator Pattern** (SDK-compliant, recommended for new tools)
2. **JSON Config Pattern** (Legacy, for enterprise configuration management)

## Quick Start

### Decorator Pattern (Recommended)

Create a `tools.py` file in your tool's directory:

```python
# src/my_tool/tools.py
from typing import Annotated
from pydantic import Field
from src.loaders.decorators import register_tool

@register_tool(name="my_tool", tags=["category"])
def my_tool(
    query: Annotated[str, Field(description="The search query")],
    limit: Annotated[int, Field(description="Max results")] = 10,
) -> str:
    """Search for information based on the query."""
    # Your implementation here
    return f"Found results for: {query}"
```

That's it! The tool is auto-discovered and registered when the agent starts.

## Decorator Pattern (SDK-Compliant)

The decorator pattern follows Microsoft SDK best practices using type hints for automatic schema generation.

### Basic Structure

```python
from typing import Annotated
from pydantic import Field
from src.loaders.decorators import register_tool

@register_tool(name="tool_name", tags=["tag1", "tag2"])
def tool_name(
    param1: Annotated[str, Field(description="Parameter description")],
    param2: Annotated[bool, Field(description="Optional flag")] = False,
) -> str:
    """
    Tool docstring becomes the AI's understanding of what this tool does.

    Be clear and specific about when and how to use this tool.
    """
    # Implementation
    return "result"
```

### Key Components

| Component | Purpose |
|-----------|---------|
| `@register_tool` | Registers the function for auto-discovery |
| `Annotated[Type, Field(...)]` | Defines parameter type and description |
| Docstring | Becomes the tool's description for the LLM |
| Return type hint | Documents expected output type |

### Parameter Validation

Use Pydantic Field constraints for validation:

```python
@register_tool(name="validated_tool")
def validated_tool(
    count: Annotated[int, Field(description="Item count", ge=1, le=100)] = 10,
    category: Annotated[str, Field(description="Category", pattern="^[a-z]+$")] = "default",
) -> str:
    """Tool with validated parameters."""
    return f"Processing {count} items in {category}"
```

### Tags for Organization

Tags help categorize and filter tools:

```python
@register_tool(name="data_fetch", tags=["data", "read-only"])
def data_fetch(...): ...

@register_tool(name="data_write", tags=["data", "write"])
def data_write(...): ...

# Filter tools by tag
from src.loaders.decorators import get_tools_by_tag
readonly_tools = get_tools_by_tag("read-only")
```

### Disabling Tools

Temporarily disable a tool without removing code:

```python
@register_tool(name="experimental_tool", enabled=False)
def experimental_tool(...):
    """This tool won't be registered."""
    ...
```

## JSON Config Pattern (Legacy)

The JSON config pattern separates configuration from implementation, useful for enterprise environments needing external configuration management.

### Directory Structure

```
config/tools/my_tool.json    # Tool configuration
src/my_tool/service.py       # Service implementation
src/my_tool/__init__.py      # Package exports
```

### Configuration File

```json
{
  "function": {
    "name": "my_tool",
    "description": "Description of what the tool does",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "The search query"
        },
        "limit": {
          "type": "integer",
          "description": "Maximum number of results"
        }
      },
      "required": ["query"]
    }
  }
}
```

### Service Implementation

```python
# src/my_tool/service.py
from typing import Any, Dict

class MyToolService:
    """Service class for my_tool."""

    def __init__(self):
        # Initialize resources
        pass

    def run(self, tool_call: Dict[str, Any]) -> str:
        """Execute the tool with provided parameters."""
        query = tool_call.get("query", "")
        limit = tool_call.get("limit", 10)

        # Your implementation
        return f"Results for {query} (limit: {limit})"


def get_my_tool_service() -> MyToolService:
    """Factory function for service instantiation."""
    return MyToolService()
```

## Configuration

Configure tool loading in `config/agent.toml`:

```toml
[agent.tools]
config_dir = "config/tools"            # JSON config directory
enable_json_tools = true               # Load JSON config tools
enable_decorator_tools = true          # Load decorator tools
# tool_modules = ["src.custom.tools"]  # Explicit module paths
```

### Hybrid Mode

Both patterns can be used together. When a tool name exists in both patterns, the **decorator tool takes precedence**.

## Pattern Comparison

| Consideration | Decorator Pattern | JSON Config Pattern |
|---------------|-------------------|---------------------|
| Type Safety | IDE autocomplete, static analysis | Manual validation |
| Configuration | Code-based | External files |
| Validation | Automatic via Pydantic | Manual in service |
| Enterprise Config | Requires code deploy | File-based updates |
| Development Speed | Fast iteration | Moderate |
| SDK Compliance | Full | Partial |

### When to Use Each Pattern

**Use Decorator Pattern when:**
- Building new tools
- Type safety and IDE support are important
- Rapid development is needed
- Team is comfortable with Python decorators

**Use JSON Config Pattern when:**
- External configuration management is required
- Non-developers need to modify tool parameters
- Enterprise change control processes apply
- Migrating from existing JSON-based systems

## Migration Guide

### Migrating from JSON Config to Decorator

1. Create `tools.py` in your tool's directory
2. Convert the JSON schema to Annotated parameters
3. Move the service logic into the decorated function
4. Update `__init__.py` to export the new function
5. Test both patterns work (hybrid mode)
6. Remove JSON config when ready

**Before (JSON Config):**
```json
{
  "function": {
    "name": "search",
    "description": "Search for documents",
    "parameters": {
      "properties": {
        "query": {"type": "string", "description": "Search query"}
      }
    }
  }
}
```

**After (Decorator):**
```python
@register_tool(name="search")
def search(
    query: Annotated[str, Field(description="Search query")],
) -> str:
    """Search for documents."""
    return perform_search(query)
```

## Testing Tools

### Unit Testing Decorator Tools

```python
import pytest
from src.my_tool.tools import my_tool

def test_my_tool_basic():
    result = my_tool(query="test")
    assert "test" in result

def test_my_tool_with_limit():
    result = my_tool(query="test", limit=5)
    assert "test" in result
```

### Testing Tool Registration

```python
from src.loaders.decorators import get_registered_tools, clear_registry

def test_tool_registered():
    # Import triggers registration
    from src.my_tool.tools import my_tool

    tools = get_registered_tools()
    assert "my_tool" in tools

def test_tool_metadata():
    from src.loaders.decorators import get_tool_metadata

    metadata = get_tool_metadata("my_tool")
    assert metadata is not None
    assert "category" in metadata.get("tags", [])
```

## Best Practices

1. **Clear Docstrings**: The docstring becomes the LLM's understanding of the tool
2. **Descriptive Parameters**: Use Field descriptions that help the LLM understand usage
3. **Validation**: Use Pydantic constraints (ge, le, pattern) for parameter validation
4. **Error Handling**: Return helpful error messages as strings
5. **Idempotency**: Design tools to be safely retried
6. **Logging**: Use structlog for consistent logging
7. **Testing**: Write unit tests for all tools

## Example: Complete Tool Implementation

See `src/example_tool/tools.py` for a complete working example demonstrating:
- Basic tool with optional parameters
- Parameter validation
- Proper docstrings
- Tag usage
