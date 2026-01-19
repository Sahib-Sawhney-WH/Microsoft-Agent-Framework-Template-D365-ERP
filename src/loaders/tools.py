"""
Dynamic tool loading system for registering service-based tools with LLM agents.

Supports two tool patterns:
1. Decorator Pattern (SDK-compliant): Using @register_tool and @ai_function
2. JSON Config Pattern (Legacy): Using config/tools/*.json with service classes

Both patterns can be used together (hybrid mode) with decorator tools
taking precedence on name conflicts.
"""
import json
import inspect
import structlog
from pathlib import Path
from typing import Dict, Any, Callable, List, Optional, Set
from importlib import import_module

from .decorators import (
    discover_decorator_tools,
    get_registered_tools,
    load_tool_modules,
)

logger = structlog.get_logger(__name__)


def load_tool_configs(config_dir: str = "config/tools") -> Dict[str, Dict[str, Any]]:
    """Load all tool configurations from directory."""
    configs = {}
    config_path = Path(config_dir)
    
    if not config_path.exists():
        return configs
    
    # Look for *.json files (tool configs named after tool)
    for file_path in config_path.glob("*.json"):
        # Tool name is the filename without .json (e.g., fabric_data.json → fabric_data)
        tool_name = file_path.stem
        
        try:
            with open(file_path) as f:
                configs[tool_name] = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse tool config file (invalid JSON)",
                tool_name=tool_name,
                file_path=str(file_path),
                error=str(e)
            )
        except Exception as e:
            logger.error(
                "Failed to load tool config file",
                tool_name=tool_name,
                file_path=str(file_path),
                error=str(e),
                exc_info=True
            )
    
    return configs


def service_name_to_class_name(service_name: str) -> str:
    """Convert snake_case to PascalCaseService."""
    parts = service_name.split("_")
    return "".join(p.capitalize() for p in parts) + "Service"


def get_or_create_service(assistant: Any, service_name: str) -> Optional[Any]:
    """Get service from assistant or create dynamically."""
    service_attr = f"{service_name}_service"
    
    # Check if service already exists on assistant
    if hasattr(assistant, service_attr):
        inst = getattr(assistant, service_attr)
        if inst is not None:
            logger.info("Found pre-initialized service", service_attr=service_attr)
            return inst
    
    # Try to dynamically create service
    try:
        class_name = service_name_to_class_name(service_name)
        module_path = f"src.{service_name}.service"
        
        logger.info("Attempting to load service dynamically", module_path=module_path, class_name=class_name)
        
        module = import_module(module_path)
        
        # Try factory function first
        factory_name = f"get_{service_name}_service"
        factory = getattr(module, factory_name, None)
        if factory:
            logger.info("Found factory function", factory_name=factory_name)
            service_instance = factory()
            logger.info("Created service via factory", service_attr=service_attr)
            return service_instance
        
        # Fall back to class instantiation
        service_class = getattr(module, class_name)
        service_instance = service_class()
        logger.info("Created service via class instantiation", class_name=class_name)
        return service_instance
        
    except Exception as e:
        logger.error("Failed to create service dynamically", 
                    service_name=service_name, 
                    error=str(e),
                    exc_info=True)
        return None


def create_tool_function(
    tool_name: str,
    tool_config: Dict[str, Any],
    service_instance: Any,
    service_method: str = "run"
) -> Callable:
    """Create tool function that calls service method via clean wrapper."""
    func_cfg = tool_config.get("function", {})
    func_name = func_cfg.get("name", tool_name)
    func_desc = func_cfg.get("description", "")
    params_cfg = func_cfg.get("parameters", {})
    properties = params_cfg.get("properties", {})
    
    # Create docstring with full description
    docstring = func_desc
    if properties:
        docstring += "\n\nParameters:"
        for param_name, param_info in properties.items():
            param_desc = param_info.get("description", "")
            docstring += f"\n  {param_name}: {param_desc}"
    
    # Build signature using inspect for introspection
    param_names = list(properties.keys())
    params = [inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)
              for name in param_names]
    sig = inspect.Signature(params, return_annotation=str)
    
    def tool_wrapper(*args, **kwargs) -> str:
        """Generic tool wrapper that calls the service method."""
        try:
            # Bind arguments to signature and convert to dict
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            tool_call = dict(bound.arguments)
            
            logger.debug("Tool function called", tool_name=tool_name, tool_call=tool_call)
            method = getattr(service_instance, service_method)
            result = method(tool_call=tool_call)
            logger.debug("Tool function result", tool_name=tool_name, result=result)
            return result
        except Exception as e:
            logger.error("Tool function error", tool_name=tool_name, error=str(e), exc_info=True)
            return f"Error: {str(e)}"
    
    # Set metadata for introspection
    tool_wrapper.__name__ = func_name
    tool_wrapper.__doc__ = docstring
    tool_wrapper.__signature__ = sig
    tool_wrapper._params = properties
    
    return tool_wrapper


def load_decorator_tools(
    assistant: Any,
    tool_modules: Optional[List[str]] = None,
    tools_dir: str = "src",
) -> int:
    """
    Load and register decorator-based tools with assistant.
    
    Discovers tools decorated with @register_tool either by:
    1. Scanning for tools.py files in the tools_dir (auto-discovery)
    2. Explicitly importing specified tool_modules
    
    Args:
        assistant: The assistant instance with a tools list.
        tool_modules: Optional explicit list of module paths to load.
        tools_dir: Directory to scan for tools.py files.
        
    Returns:
        Number of decorator tools registered.
    """
    if not hasattr(assistant, "tools"):
        return 0
    
    # Get already registered tool names to avoid duplicates
    existing_names: Set[str] = {
        getattr(t, "__name__", getattr(t, "_tool_name", None))
        for t in assistant.tools
    }
    
    # Load tools via explicit modules or auto-discovery
    if tool_modules:
        load_tool_modules(tool_modules)
    else:
        discover_decorator_tools(tools_dir=tools_dir)
    
    # Get all registered decorator tools
    decorator_tools = get_registered_tools()
    registered = 0
    
    for tool_name, tool_func in decorator_tools.items():
        # Skip if already registered
        if tool_name in existing_names:
            logger.debug(
                "Skipping decorator tool (already registered)",
                tool_name=tool_name
            )
            continue
        
        assistant.tools.append(tool_func)
        registered += 1
        logger.debug("Registered decorator tool", tool_name=tool_name)
    
    return registered


def load_json_config_tools(
    assistant: Any,
    config_dir: str = "config/tools",
    service_method: str = "run",
    skip_names: Optional[Set[str]] = None,
) -> int:
    """
    Load and register JSON config-based tools with assistant.
    
    Args:
        assistant: The assistant instance with a tools list.
        config_dir: Directory containing tool JSON configs.
        service_method: Method name to call on service instances.
        skip_names: Tool names to skip (e.g., already registered decorator tools).
        
    Returns:
        Number of JSON config tools registered.
    """
    if not hasattr(assistant, "tools"):
        return 0
    
    skip_names = skip_names or set()
    tool_configs = load_tool_configs(config_dir)
    registered = 0
    
    for tool_name, config in tool_configs.items():
        # Skip if decorator tool with same name exists (decorator takes precedence)
        if tool_name in skip_names:
            logger.debug(
                "Skipping JSON tool (decorator tool takes precedence)",
                tool_name=tool_name
            )
            continue
        
        try:
            service = get_or_create_service(assistant, tool_name)
            if not service:
                continue
            
            fn = create_tool_function(tool_name, config, service, service_method)
            assistant.tools.append(fn)
            registered += 1
            logger.debug("Registered JSON config tool", tool_name=tool_name)
        except Exception as e:
            logger.error(
                "Failed to register JSON config tool",
                tool_name=tool_name,
                error=str(e)
            )
    
    return registered


def load_and_register_tools(
    assistant: Any,
    config_dir: str = "config/tools",
    tool_modules: Optional[List[str]] = None,
    enable_decorator_tools: bool = True,
    enable_json_tools: bool = True,
    service_method: str = "run",
) -> int:
    """
    Load and register all tools with assistant (hybrid loader).
    
    Supports both decorator-based (SDK-compliant) and JSON config-based (legacy)
    tool patterns. When both are enabled, decorator tools take precedence on
    name conflicts.
    
    Args:
        assistant: The assistant instance with a tools list.
        config_dir: Directory containing JSON tool configs.
        tool_modules: Optional explicit list of module paths for decorator tools.
        enable_decorator_tools: Whether to load decorator-based tools.
        enable_json_tools: Whether to load JSON config-based tools.
        service_method: Method name to call on service instances.
        
    Returns:
        Total number of tools registered.
    """
    if not hasattr(assistant, "tools"):
        return 0
    
    total_registered = 0
    decorator_tool_names: Set[str] = set()
    
    # Load decorator tools first (they take precedence)
    if enable_decorator_tools:
        decorator_count = load_decorator_tools(
            assistant,
            tool_modules=tool_modules,
        )
        total_registered += decorator_count
        
        # Track decorator tool names for conflict resolution
        decorator_tool_names = set(get_registered_tools().keys())
        
        logger.info(
            "Decorator tools loaded",
            count=decorator_count,
            tool_names=list(decorator_tool_names)
        )
    
    # Load JSON config tools (skipping conflicts)
    if enable_json_tools:
        json_count = load_json_config_tools(
            assistant,
            config_dir=config_dir,
            service_method=service_method,
            skip_names=decorator_tool_names,
        )
        total_registered += json_count
        
        logger.info("JSON config tools loaded", count=json_count)
    
    logger.info(
        "Tool loading complete",
        total_tools=total_registered,
        decorator_tools=len(decorator_tool_names) if enable_decorator_tools else 0,
        json_tools=total_registered - len(decorator_tool_names) if enable_decorator_tools else total_registered,
    )
    
    return total_registered
