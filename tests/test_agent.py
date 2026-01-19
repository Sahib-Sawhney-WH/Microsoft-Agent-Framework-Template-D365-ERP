"""
Tests for the AI Assistant.

Run tests with: pytest tests/ -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestExampleToolService:
    """Tests for the example tool service."""
    
    def test_service_initialization(self):
        """Test that service initializes correctly."""
        from src.example_tool.service import ExampleToolService
        
        service = ExampleToolService(prefix="[Test]")
        assert service.prefix == "[Test]"
    
    def test_run_basic_message(self):
        """Test basic message processing."""
        from src.example_tool.service import ExampleToolService
        
        service = ExampleToolService()
        result = service.run({"message": "Hello World"})
        
        assert "Hello World" in result
        assert "Processed message" in result
    
    def test_run_uppercase(self):
        """Test uppercase processing."""
        from src.example_tool.service import ExampleToolService
        
        service = ExampleToolService()
        result = service.run({"message": "hello", "uppercase": True})
        
        assert "HELLO" in result
    
    def test_run_missing_message(self):
        """Test error handling for missing message."""
        from src.example_tool.service import ExampleToolService
        
        service = ExampleToolService()
        result = service.run({})
        
        assert "Error" in result
        assert "required" in result.lower()
    
    def test_factory_function(self):
        """Test the factory function returns singleton."""
        from src.example_tool.service import get_example_tool_service
        
        service1 = get_example_tool_service()
        service2 = get_example_tool_service()
        
        assert service1 is service2


class TestToolLoader:
    """Tests for the dynamic tool loader."""
    
    def test_load_tool_configs(self):
        """Test loading tool configs from directory."""
        from src.loaders import load_tool_configs
        
        configs = load_tool_configs("config/tools")
        assert "example_tool" in configs
    
    def test_service_name_to_class_name(self):
        """Test service name conversion."""
        from src.loaders.tools import service_name_to_class_name
        
        assert service_name_to_class_name("example_tool") == "ExampleToolService"
        assert service_name_to_class_name("weather") == "WeatherService"
        assert service_name_to_class_name("my_cool_api") == "MyCoolApiService"


class TestConfig:
    """Tests for configuration loading."""
    
    def test_load_config_from_toml(self):
        """Test loading config from agent.toml."""
        from src.config import load_config
        
        # This will load from config/agent.toml
        config = load_config("config/agent.toml")
        
        assert config.system_prompt_file == "config/system_prompt.txt"
        assert config.tools_config_dir == "config/tools"
    
    def test_env_override(self):
        """Test that environment variables override config."""
        import os
        from src.config import AgentConfig
        
        # Set env var
        os.environ["AZURE_OPENAI_ENDPOINT"] = "https://test.openai.azure.com/"
        
        config = AgentConfig({
            "azure_openai": {"endpoint": "https://config.openai.azure.com/"}
        })
        
        # Env should take precedence
        assert config.azure_openai_endpoint == "https://test.openai.azure.com/"
        
        # Cleanup
        del os.environ["AZURE_OPENAI_ENDPOINT"]
