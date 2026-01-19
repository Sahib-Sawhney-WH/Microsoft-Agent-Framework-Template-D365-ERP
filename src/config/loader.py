"""
Configuration management using TOML files.

Loads agent configuration from config/agent.toml or pyproject.toml.
Environment variables can override TOML settings with AGENT_ prefix.

Supports:
- Multi-model provider configuration
- MCP session management configuration
- Legacy Azure OpenAI backward compatibility
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

# Python 3.11+ has tomllib built-in, otherwise use tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        raise ImportError("Please install 'tomli' for Python < 3.11: pip install tomli")

logger = structlog.get_logger(__name__)


class AgentConfig:
    """Configuration container for the AI Agent."""
    
    def __init__(self, config_dict: Dict[str, Any]):
        """Initialize configuration from dictionary."""
        self._config = config_dict
        
        # Core settings
        self.system_prompt_file = self._get("system_prompt", "config/system_prompt.txt")
        self.log_level = self._get("log_level", "INFO")
        self.default_model = self._get("default_model", None)
        
        # Azure OpenAI settings (legacy support)
        azure_config = self._config.get("azure_openai", {})
        self.azure_openai_endpoint = self._get_env_or_config(
            "AZURE_OPENAI_ENDPOINT", 
            azure_config.get("endpoint", "")
        )
        self.azure_openai_deployment = self._get_env_or_config(
            "AZURE_OPENAI_DEPLOYMENT",
            azure_config.get("deployment", "")
        )
        self.azure_openai_api_version = self._get_env_or_config(
            "AZURE_OPENAI_API_VERSION",
            azure_config.get("api_version", "2024-10-01-preview")
        )
        
        # Multi-model configuration
        from src.models.providers import parse_model_configs
        self.model_configs, self._default_model_name = parse_model_configs(self._config)
        if self._default_model_name:
            self.default_model = self._default_model_name
        
        # Tools settings (hybrid loading support)
        tools_config = self._config.get("tools", {})
        self.tools_config_dir = tools_config.get("config_dir", "config/tools")
        self.enable_json_tools = tools_config.get("enable_json_tools", True)
        self.enable_decorator_tools = tools_config.get("enable_decorator_tools", True)
        self.tool_modules = tools_config.get("tool_modules", None)
        self.tool_settings = {
            k: v for k, v in tools_config.items() 
            if isinstance(v, dict)
        }
        
        # MCP settings
        from src.loaders.mcp import parse_mcp_configs
        self.mcp_configs = parse_mcp_configs(self._config)
        
        # MCP session settings
        from src.mcp.session import parse_mcp_session_config
        self.mcp_session_config = parse_mcp_session_config(self._config)
        
        # Workflow settings
        from src.loaders.workflows import parse_workflow_configs
        self.workflow_configs = parse_workflow_configs(self._config)
        
        # Memory settings (cache + persistence)
        from src.memory.manager import parse_memory_config
        self.memory_config = parse_memory_config(self._config)

        
    def _get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with default."""
        return self._config.get(key, default)
    
    def _get_env_or_config(self, env_key: str, config_value: str) -> str:
        """Get value from environment variable or config, env takes precedence."""
        return os.getenv(env_key, config_value)
    
    def get_tool_config(self, tool_name: str) -> Dict[str, Any]:
        """Get configuration for a specific tool."""
        return self.tool_settings.get(tool_name, {})
    
    def validate(self) -> None:
        """Validate required configuration values."""
        errors = []
        
        # Check for multi-model config first
        has_multi_model = bool(self.model_configs)
        has_legacy_azure = bool(self.azure_openai_endpoint and self.azure_openai_deployment)
        
        if not has_multi_model and not has_legacy_azure:
            errors.append(
                "No model configuration found. Either:\n"
                "  1. Configure [[agent.models]] sections for multi-model support, or\n"
                "  2. Set [agent.azure_openai] endpoint and deployment for legacy mode, or\n"
                "  3. Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT env vars"
            )
        
        if errors:
            for error in errors:
                logger.error("Configuration error", error=error)
            raise ValueError("Configuration validation failed:\n" + "\n".join(errors))
        
        # Log configuration summary
        if has_multi_model:
            model_names = [m.get("name", "unnamed") for m in self.model_configs]
            logger.info(
                "Configuration validated (multi-model)",
                models=model_names,
                default=self.default_model
            )
        else:
            logger.info(
                "Configuration validated (legacy Azure OpenAI)",
                endpoint=self.azure_openai_endpoint[:30] + "..." if self.azure_openai_endpoint else None,
                deployment=self.azure_openai_deployment
            )


def load_config(config_path: Optional[str] = None) -> AgentConfig:
    """
    Load agent configuration from TOML file.
    
    Searches in order:
    1. Explicit config_path if provided
    2. config/agent.toml
    3. pyproject.toml [tool.agent] section
    
    Args:
        config_path: Optional explicit path to config file
        
    Returns:
        AgentConfig instance with loaded configuration
        
    Raises:
        FileNotFoundError: If no config file found
        ValueError: If configuration is invalid
    """
    config_dict: Dict[str, Any] = {}
    
    # List of paths to try
    search_paths = []
    
    if config_path:
        search_paths.append(Path(config_path))
    
    search_paths.extend([
        Path("config/agent.toml"),
        Path("pyproject.toml"),
    ])
    
    for path in search_paths:
        if path.exists():
            logger.info("Loading configuration", path=str(path))
            
            with open(path, "rb") as f:
                data = tomllib.load(f)
            
            # Check if it's pyproject.toml (need to look under [tool.agent])
            if path.name == "pyproject.toml":
                config_dict = data.get("tool", {}).get("agent", {})
                if not config_dict:
                    logger.debug("No [tool.agent] section in pyproject.toml")
                    continue
            else:
                # Direct agent.toml uses [agent] section
                config_dict = data.get("agent", {})
            
            if config_dict:
                logger.info("Configuration loaded successfully", path=str(path))
                break
    
    if not config_dict:
        raise FileNotFoundError(
            "No configuration found. Create config/agent.toml or add [tool.agent] to pyproject.toml"
        )
    
    return AgentConfig(config_dict)


# Global config instance (lazy loaded)
_config: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
