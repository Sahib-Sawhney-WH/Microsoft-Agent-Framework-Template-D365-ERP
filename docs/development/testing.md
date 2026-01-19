# Testing Guide

This guide covers running and writing tests for the MSFT Agent Framework.

## Prerequisites

Install development dependencies:

```bash
pip install -e ".[dev]"
```

This includes:
- pytest
- pytest-asyncio
- pytest-cov
- pytest-mock

---

## Running Tests

### All Tests

```bash
pytest tests/ -v
```

### Specific Test Files

```bash
pytest tests/unit/test_assistant.py -v
```

### Specific Test Functions

```bash
pytest tests/unit/test_assistant.py::test_process_question -v
```

### By Marker

```bash
# Skip slow tests
pytest tests/ -m "not slow"

# Only integration tests
pytest tests/ -m integration

# Only unit tests
pytest tests/ -m "not integration"
```

### With Coverage

```bash
# Generate coverage report
pytest tests/ --cov=src --cov-report=html

# View coverage
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

### Parallel Execution

```bash
pip install pytest-xdist
pytest tests/ -n auto  # Use all CPU cores
```

---

## Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── unit/                 # Unit tests
│   ├── test_assistant.py
│   ├── test_config.py
│   ├── test_tools.py
│   └── test_memory.py
└── integration/          # Integration tests
    ├── test_azure_openai.py
    ├── test_redis.py
    └── test_mcp.py
```

---

## Writing Tests

### Basic Test Structure

```python
# tests/unit/test_example.py
import pytest
from src.example import MyClass

def test_basic_functionality():
    """Test basic functionality."""
    obj = MyClass()
    result = obj.do_something("input")
    assert result == "expected"

def test_edge_case():
    """Test edge case handling."""
    obj = MyClass()
    with pytest.raises(ValueError):
        obj.do_something("")
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    """Test async functionality."""
    result = await some_async_function()
    assert result is not None
```

### Using Fixtures

```python
# conftest.py
import pytest
from src.config import AgentConfig

@pytest.fixture
def sample_config():
    """Provide a sample configuration."""
    return AgentConfig(
        default_model="test",
        log_level="DEBUG"
    )

@pytest.fixture
async def assistant(sample_config):
    """Provide an initialized assistant."""
    from src.agent import AIAssistant
    async with AIAssistant(config=sample_config) as assistant:
        yield assistant
```

```python
# test_assistant.py
@pytest.mark.asyncio
async def test_with_assistant(assistant):
    """Test using the assistant fixture."""
    result = await assistant.process_question("Hello")
    assert result.response is not None
```

### Mocking

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mock():
    """Test with mocked Azure OpenAI."""
    with patch("src.agent.assistant.AzureOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(
            return_value=MockResponse(content="Mocked response")
        )

        async with AIAssistant() as assistant:
            result = await assistant.process_question("Hello")
            assert result.response == "Mocked response"
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("test", "TEST"),
])
def test_uppercase(input, expected):
    """Test uppercase transformation."""
    assert input.upper() == expected
```

---

## Test Categories

### Unit Tests

Test individual functions and classes in isolation:

```python
# tests/unit/test_tools.py
from src.tools import ai_function

def test_ai_function_decorator():
    """Test the ai_function decorator."""
    @ai_function
    def my_tool(x: int) -> int:
        """Add one."""
        return x + 1

    assert my_tool(1) == 2
    assert hasattr(my_tool, "__ai_function__")
```

### Integration Tests

Test interactions with external services:

```python
# tests/integration/test_azure_openai.py
import pytest
import os

@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("AZURE_OPENAI_ENDPOINT"),
    reason="Azure OpenAI not configured"
)
@pytest.mark.asyncio
async def test_azure_openai_connection():
    """Test connection to Azure OpenAI."""
    from src.agent import AIAssistant

    async with AIAssistant() as assistant:
        health = await assistant.health_check()
        azure_health = next(
            (c for c in health.components if c.name == "azure_openai"),
            None
        )
        assert azure_health is not None
        assert azure_health.status == "healthy"
```

### Slow Tests

Mark tests that take a long time:

```python
@pytest.mark.slow
@pytest.mark.asyncio
async def test_long_running_operation():
    """Test that takes a while."""
    result = await perform_slow_operation()
    assert result is not None
```

---

## Fixtures Reference

### Common Fixtures

```python
# conftest.py

@pytest.fixture
def mock_config():
    """Minimal configuration for testing."""
    return AgentConfig(
        default_model="test",
        log_level="DEBUG",
        models=[
            ModelConfig(
                name="test",
                provider="azure_openai",
                endpoint="https://test.openai.azure.com/",
                deployment="test-model"
            )
        ]
    )

@pytest.fixture
def mock_response():
    """Mock OpenAI response."""
    return MockChatCompletion(
        choices=[
            MockChoice(
                message=MockMessage(content="Test response")
            )
        ],
        usage=MockUsage(total_tokens=10)
    )

@pytest.fixture
async def redis_client():
    """Provide a Redis client for testing."""
    import redis.asyncio as redis
    client = redis.from_url("redis://localhost:6379")
    yield client
    await client.flushdb()  # Clean up after test
    await client.close()
```

### Fixture Scopes

```python
@pytest.fixture(scope="session")
def expensive_resource():
    """Created once per test session."""
    return create_expensive_thing()

@pytest.fixture(scope="module")
def module_resource():
    """Created once per test module."""
    return create_thing()

@pytest.fixture(scope="function")  # Default
def function_resource():
    """Created for each test function."""
    return create_thing()
```

---

## Testing Async Code

### Basic Async Test

```python
@pytest.mark.asyncio
async def test_async():
    result = await async_function()
    assert result == expected
```

### Async Fixtures

```python
@pytest.fixture
async def async_resource():
    resource = await create_resource()
    yield resource
    await resource.cleanup()
```

### Testing Streams

```python
@pytest.mark.asyncio
async def test_streaming():
    chunks = []
    async for chunk in await assistant.process_question_stream("Hello"):
        chunks.append(chunk.text)

    full_response = "".join(chunks)
    assert len(full_response) > 0
```

---

## Mocking External Services

### Mock Azure OpenAI

```python
@pytest.fixture
def mock_openai(mocker):
    mock = mocker.patch("openai.AsyncAzureOpenAI")
    mock_instance = mock.return_value
    mock_instance.chat.completions.create = AsyncMock(
        return_value=create_mock_response("Test response")
    )
    return mock_instance
```

### Mock Redis

```python
@pytest.fixture
def mock_redis(mocker):
    mock = mocker.patch("redis.asyncio.from_url")
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.set = AsyncMock(return_value=True)
    mock.return_value = mock_client
    return mock_client
```

### Mock MCP Server

```python
@pytest.fixture
def mock_mcp(mocker):
    mock = mocker.patch("src.loaders.mcp.MCPClient")
    mock_instance = mock.return_value
    mock_instance.list_tools = AsyncMock(return_value=[
        {"name": "test_tool", "description": "Test"}
    ])
    mock_instance.call_tool = AsyncMock(return_value={"result": "ok"})
    return mock_instance
```

---

## Test Configuration

### pytest.ini / pyproject.toml

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --tb=short"
markers = [
    "slow: marks tests as slow",
    "integration: marks tests as integration tests",
]
```

### Coverage Configuration

```toml
[tool.coverage.run]
source = ["src"]
omit = ["tests/*", "*/__pycache__/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

---

## CI/CD Testing

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        run: pytest tests/ -v --cov=src

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Troubleshooting Tests

### Test Discovery Issues

```bash
# Verify pytest finds tests
pytest --collect-only

# Check for import errors
python -c "from tests.unit.test_assistant import *"
```

### Async Test Failures

```
# Error: "coroutine was never awaited"
# Solution: Add @pytest.mark.asyncio decorator

# Error: "Event loop is closed"
# Solution: Use pytest-asyncio with scope="function"
```

### Mock Not Working

```python
# Make sure to patch where it's used, not where it's defined
# Wrong:
@patch("src.models.azure_openai.AzureOpenAI")

# Right:
@patch("src.agent.assistant.AzureOpenAI")
```

---

## Related Documentation

- [Contributing](contributing.md) — Development workflow
- [Architecture](../architecture.md) — System design

---
*Last updated: 2026-01-17*
