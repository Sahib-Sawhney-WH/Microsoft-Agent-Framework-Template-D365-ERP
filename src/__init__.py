"""MSFT Agent Framework - Extensible AI Assistant."""

from src.agent import AIAssistant, process_query
from src.config import AgentConfig, get_config, load_config

__all__ = [
    "AIAssistant", 
    "process_query",
    "AgentConfig",
    "get_config",
    "load_config",
]
