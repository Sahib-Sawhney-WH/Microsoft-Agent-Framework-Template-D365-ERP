"""
Pytest configuration and shared fixtures.

Provides common fixtures for testing the AI Assistant.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone


# Configure pytest-asyncio
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== Mock Azure OpenAI ====================

@pytest.fixture
def mock_chat_client():
    """Mock Azure OpenAI chat client."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(
            message=MagicMock(content="Test response")
        )],
        usage=MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )
    ))
    return client


@pytest.fixture
def mock_agent():
    """Mock ChatAgent."""
    agent = MagicMock()
    agent.name = "TestAgent"
    agent.get_new_thread = MagicMock(return_value=MagicMock())
    agent.run = AsyncMock(return_value=MagicMock(
        text="Test response",
        content="Test response"
    ))
    agent.run_stream = AsyncMock()
    agent.deserialize_thread = AsyncMock(return_value=MagicMock())
    return agent


@pytest.fixture
def mock_thread():
    """Mock conversation thread."""
    thread = MagicMock()
    thread.messages = []
    thread.serialize = AsyncMock(return_value={
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
    })
    return thread


# ==================== Mock Memory Components ====================

@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.ping = AsyncMock(return_value=True)
    client.scan = AsyncMock(return_value=(0, []))
    client.ttl = AsyncMock(return_value=3600)
    return client


@pytest.fixture
def mock_cache(mock_redis_client):
    """Mock cache with Redis client."""
    from src.memory.cache import CacheConfig

    cache = MagicMock()
    cache._client = mock_redis_client
    cache.config = CacheConfig(enabled=True)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    cache.close = AsyncMock()
    return cache


@pytest.fixture
def mock_persistence():
    """Mock ADLS persistence."""
    persistence = MagicMock()
    persistence.config = MagicMock(enabled=True)
    persistence.get = AsyncMock(return_value=None)
    persistence.save = AsyncMock(return_value=True)
    persistence.delete = AsyncMock(return_value=True)
    persistence.list_chats = AsyncMock(return_value=[])
    persistence.close = AsyncMock()
    return persistence


# ==================== Configuration Fixtures ====================

@pytest.fixture
def memory_config():
    """Create test memory configuration."""
    from src.memory.manager import MemoryConfig, SummarizationConfig
    from src.memory.cache import CacheConfig
    from src.memory.persistence import PersistenceConfig

    return MemoryConfig(
        cache=CacheConfig(enabled=False),
        persistence=PersistenceConfig(enabled=False),
        summarization=SummarizationConfig(enabled=True, max_tokens=1000)
    )


@pytest.fixture
def tracing_config():
    """Create test tracing configuration."""
    from src.observability.tracing import TracingConfig

    return TracingConfig(
        enabled=True,
        service_name="test-service",
        exporter_type="none"
    )


@pytest.fixture
def rate_limit_config():
    """Create test rate limit configuration."""
    from src.security.rate_limiter import RateLimiterConfig

    return RateLimiterConfig(
        requests_per_minute=100,
        requests_per_hour=1000,
        max_concurrent_requests=10
    )


@pytest.fixture
def validator_config():
    """Create test validator configuration."""
    from src.security.input_validator import ValidatorConfig

    return ValidatorConfig(
        detect_injection=True,
        sanitize_pii=True,
        max_input_length=10000
    )


# ==================== Health Check Fixtures ====================

@pytest.fixture
def health_config():
    """Create test health check configuration."""
    from src.health import HealthCheckConfig

    return HealthCheckConfig(
        enabled=True,
        timeout_seconds=5.0,
        cache_seconds=0.0,  # Disable caching for tests
        version="test-1.0.0"
    )


@pytest.fixture
def health_checker(health_config):
    """Create health checker instance."""
    from src.health import HealthChecker

    return HealthChecker(health_config)


# ==================== Workflow Fixtures ====================

@pytest.fixture
def workflow_manager(mock_chat_client):
    """Create workflow manager with mock client."""
    from src.loaders.workflows import WorkflowManager

    return WorkflowManager(mock_chat_client)


@pytest.fixture
def sample_workflow_config():
    """Sample workflow configuration."""
    return {
        "name": "test-workflow",
        "type": "custom",
        "start": "Triage",
        "agents": [
            {"name": "Triage", "instructions": "Triage incoming requests"},
            {"name": "TechSupport", "instructions": "Handle technical issues"},
            {"name": "Billing", "instructions": "Handle billing issues"},
        ],
        "edges": [
            {"from": "Triage", "to": "TechSupport", "condition": "output.category == 'technical'", "priority": 1},
            {"from": "Triage", "to": "Billing", "condition": "output.category == 'billing'", "priority": 1},
        ]
    }


# ==================== Security Fixtures ====================

@pytest.fixture
def rate_limiter(rate_limit_config):
    """Create rate limiter instance."""
    from src.security.rate_limiter import RateLimiter

    return RateLimiter(rate_limit_config)


@pytest.fixture
def input_validator(validator_config):
    """Create input validator instance."""
    from src.security.input_validator import InputValidator

    return InputValidator(validator_config)


# ==================== Utility Fixtures ====================

@pytest.fixture
def sample_messages():
    """Sample conversation messages."""
    return [
        {"role": "user", "content": "Hello, I need help with Python"},
        {"role": "assistant", "content": "Of course! What would you like to know?"},
        {"role": "user", "content": "How do I create a class?"},
        {"role": "assistant", "content": "Here's how to create a class in Python..."},
    ]


@pytest.fixture
def sample_tool_config():
    """Sample tool configuration."""
    return {
        "name": "test_tool",
        "description": "A test tool for unit tests",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    }


# ==================== Environment Setup ====================

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables."""
    # Ensure we're in test mode
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    # Clear any production credentials
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
