"""
Decorator-based tool registration system for SDK-compliant tool development.

This module provides the @register_tool decorator and auto-discovery system
that enables SDK-compliant tool patterns using @ai_function with Annotated types.

Usage:
    from src.loaders.decorators import register_tool
    from typing import Annotated
    from pydantic import Field

    @register_tool(name="my_tool", tags=["demo"])
    def my_tool(
        message: Annotated[str, Field(description="Input message")],
    ) -> str:
        '''Tool docstring becomes AI's understanding.'''
        return f"Processed: {message}"
"""

import sys
import importlib
import importlib.util
import structlog
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

logger = structlog.get_logger(__name__)

# Global registry for decorated tools
_registered_tools: Dict[str, Callable] = {}
_tool_metadata: Dict[str, Dict] = {}


def register_tool(
    name: Optional[str] = None,
    tags: Optional[List[str]] = None,
    enabled: bool = True,
):
    """
    Decorator to register a tool for auto-discovery.
    
    This decorator marks a function as a tool and registers it in the global
    tool registry. Can be used alone or combined with @ai_function.
    
    Args:
        name: Tool name override. Defaults to function name.
        tags: Optional list of tags for categorization/filtering.
        enabled: Whether the tool is enabled. Disabled tools are not registered.
    
    Returns:
        Decorated function with registration metadata.
    
    Example:
        @register_tool(name="my_tool", tags=["demo"])
        @ai_function
        def my_tool(message: Annotated[str, Field(description="Input")]) -> str:
            '''Processes messages.'''
            return f"Result: {message}"
    """
    def decorator(func: Callable) -> Callable:
        if not enabled:
            logger.debug("Tool disabled, skipping registration", tool_name=name or func.__name__)
            return func
        
        tool_name = name or func.__name__
        
        # Store metadata
        _tool_metadata[tool_name] = {
            "tags": tags or [],
            "enabled": enabled,
            "source": "decorator",
            "module": func.__module__,
        }
        
        # Register the tool
        _registered_tools[tool_name] = func
        
        # Add metadata to function for introspection
        func._tool_name = tool_name
        func._tool_tags = tags or []
        func._tool_source = "decorator"
        
        logger.debug(
            "Registered decorator tool",
            tool_name=tool_name,
            tags=tags,
            module=func.__module__
        )
        
        return func
    
    return decorator


def get_registered_tools() -> Dict[str, Callable]:
    """
    Get all registered decorator-based tools.
    
    Returns:
        Dictionary mapping tool names to tool functions.
    """
    return _registered_tools.copy()


def get_tool_metadata(tool_name: str) -> Optional[Dict]:
    """
    Get metadata for a specific tool.
    
    Args:
        tool_name: Name of the tool.
        
    Returns:
        Tool metadata dict or None if not found.
    """
    return _tool_metadata.get(tool_name)


def get_tools_by_tag(tag: str) -> List[Callable]:
    """
    Get all tools with a specific tag.
    
    Args:
        tag: Tag to filter by.
        
    Returns:
        List of tool functions with the specified tag.
    """
    return [
        func for name, func in _registered_tools.items()
        if tag in _tool_metadata.get(name, {}).get("tags", [])
    ]


def clear_registry() -> None:
    """Clear all registered tools. Useful for testing."""
    _registered_tools.clear()
    _tool_metadata.clear()
    logger.debug("Tool registry cleared")


def discover_decorator_tools(
    tools_dir: str = "src",
    tool_file_pattern: str = "tools.py",
    exclude_dirs: Optional[Set[str]] = None,
) -> List[Callable]:
    """
    Scan for and import modules containing @register_tool decorated functions.
    
    This function walks through the specified directory tree, finds files
    matching the pattern (default: tools.py), and imports them to trigger
    tool registration via the @register_tool decorator.
    
    Args:
        tools_dir: Root directory to scan for tool modules.
        tool_file_pattern: Filename pattern to match (default: "tools.py").
        exclude_dirs: Set of directory names to skip (default: __pycache__, .git, etc).
        
    Returns:
        List of discovered and registered tool functions.
    """
    if exclude_dirs is None:
        exclude_dirs = {"__pycache__", ".git", ".pytest_cache", "node_modules", ".venv", "venv"}
    
    tools_path = Path(tools_dir)
    if not tools_path.exists():
        logger.warning("Tools directory not found", path=tools_dir)
        return []
    
    discovered_modules: List[str] = []
    
    # Walk directory tree
    for path in tools_path.rglob(tool_file_pattern):
        # Skip excluded directories
        if any(excluded in path.parts for excluded in exclude_dirs):
            continue
        
        # Convert path to module name
        # e.g., src/example_tool/tools.py -> src.example_tool.tools
        try:
            relative = path.relative_to(Path.cwd())
            module_name = str(relative.with_suffix("")).replace("\\", ".").replace("/", ".")
            discovered_modules.append(module_name)
        except ValueError:
            logger.warning("Could not determine module name", path=str(path))
            continue
    
    # Import discovered modules to trigger registration
    newly_registered = []
    before_count = len(_registered_tools)
    
    for module_name in discovered_modules:
        try:
            # Check if already imported
            if module_name in sys.modules:
                logger.debug("Module already imported", module=module_name)
                continue
            
            logger.debug("Importing tool module", module=module_name)
            importlib.import_module(module_name)
            
        except ImportError as e:
            logger.warning(
                "Failed to import tool module",
                module=module_name,
                error=str(e)
            )
        except Exception as e:
            logger.error(
                "Error loading tool module",
                module=module_name,
                error=str(e),
                exc_info=True
            )
    
    after_count = len(_registered_tools)
    newly_registered = list(_registered_tools.values())
    
    logger.info(
        "Tool discovery complete",
        modules_scanned=len(discovered_modules),
        tools_registered=after_count,
        new_tools=after_count - before_count
    )
    
    return newly_registered


def load_tool_modules(module_paths: List[str]) -> List[Callable]:
    """
    Explicitly load specific tool modules.
    
    This function imports the specified modules to trigger tool registration.
    Use this when you want explicit control over which modules are loaded.
    
    Args:
        module_paths: List of module paths to import (e.g., ["src.my_tool.tools"]).
        
    Returns:
        List of all registered tool functions after loading.
    """
    for module_path in module_paths:
        try:
            if module_path in sys.modules:
                # Reload to pick up changes
                importlib.reload(sys.modules[module_path])
            else:
                importlib.import_module(module_path)
            
            logger.debug("Loaded tool module", module=module_path)
            
        except ImportError as e:
            logger.error(
                "Failed to import tool module",
                module=module_path,
                error=str(e)
            )
        except Exception as e:
            logger.error(
                "Error loading tool module",
                module=module_path,
                error=str(e),
                exc_info=True
            )
    
    return list(_registered_tools.values())
