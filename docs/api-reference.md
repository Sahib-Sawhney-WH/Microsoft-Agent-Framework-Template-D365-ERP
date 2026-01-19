# API Reference

Complete API documentation for the Microsoft Agent Framework Template.

## Table of Contents

- [AIAssistant](#aiassistant)
- [Request Models](#request-models)
- [Response Models](#response-models)
- [Configuration Classes](#configuration-classes)
- [Security Components](#security-components)
- [Memory Components](#memory-components)
- [Tool Development](#tool-development)

---

## AIAssistant

The main entry point for the AI Assistant framework.

```python
from src.agent.assistant import AIAssistant
```

### Class: AIAssistant

```python
class AIAssistant:
    """
    AI Assistant with dynamic tool loading, MCP support, workflows, and service discovery.

    Uses Microsoft Agent Framework to reason across multiple data sources.
    """
```

### Constructor

```python
def __init__(self, config: AgentConfig = None) -> None
```

Initialize assistant with configuration.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `AgentConfig` | `None` | Optional configuration. If not provided, loads from `config/agent.toml` |

**Note:** MCP servers require async initialization. Call `await assistant.initialize()` after creating the instance, or use the async context manager.

### Factory Method

```python
@classmethod
async def create(cls, config: AgentConfig = None) -> "AIAssistant"
```

Factory method to create and initialize an AI Assistant.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config` | `AgentConfig` | `None` | Optional configuration instance |

**Returns:** Fully initialized `AIAssistant` instance

**Example:**
```python
assistant = await AIAssistant.create()
result = await assistant.process_question("Hello!")
```

### Async Context Manager

```python
async with await AIAssistant.create() as assistant:
    result = await assistant.process_question("Hello!")
```

Or without the factory:

```python
async with AIAssistant() as assistant:
    # auto-initializes on enter
    result = await assistant.process_question("Hello!")
```

### Methods

#### initialize

```python
async def initialize(self) -> "AIAssistant"
```

Initialize async components (MCP servers, workflows).

**Returns:** `self` for method chaining

---

#### process_question

```python
async def process_question(
    self,
    question: str,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    model: Optional[str] = None,
) -> QuestionResponse
```

Process a question using the Agent Framework.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `question` | `str` | required | User's question to process |
| `chat_id` | `str` | `None` | Session ID for conversation continuity |
| `user_id` | `str` | `None` | User ID for rate limiting |
| `model` | `str` | `None` | Model name for per-request override |

**Returns:** `QuestionResponse` with the agent's response and metadata

**Session Behavior:**
- If `chat_id` is provided and found in cache/ADLS, continues that session
- If `chat_id` is provided but not found, creates new session with that ID
- If `chat_id` is not provided, generates new UUID for the session

**Example:**
```python
# New conversation
result = await assistant.process_question("My name is Alice")

# Continue conversation
result2 = await assistant.process_question(
    "What's my name?",
    chat_id=result.chat_id
)

# Use specific model
result3 = await assistant.process_question(
    "Complex question",
    model="gpt-4o"
)
```

---

#### process_question_stream

```python
async def process_question_stream(
    self,
    question: str,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> AsyncGenerator[StreamChunk, None]
```

Process a question with streaming response.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `question` | `str` | required | User's question to process |
| `chat_id` | `str` | `None` | Session ID for conversation continuity |
| `user_id` | `str` | `None` | User ID for rate limiting |

**Yields:** `StreamChunk` objects with progressive response text

**Example:**
```python
async for chunk in assistant.process_question_stream("Tell me a story"):
    if chunk.text:
        print(chunk.text, end="", flush=True)
    if chunk.done:
        print(f"\n\nChat ID: {chunk.chat_id}")
```

---

#### run_workflow

```python
async def run_workflow(
    self,
    workflow_name: str,
    message: str,
    stream: bool = False
) -> WorkflowResponse | AsyncGenerator[WorkflowStreamChunk, None]
```

Run a named workflow with the given message.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `workflow_name` | `str` | required | Name of the workflow (from config) |
| `message` | `str` | required | Input message to process |
| `stream` | `bool` | `False` | If True, returns async generator |

**Returns:** `WorkflowResponse` or `AsyncGenerator[WorkflowStreamChunk]`

**Example:**
```python
# Non-streaming
result = await assistant.run_workflow("content-pipeline", "Write about AI")
print(result.response)

# Streaming
async for chunk in await assistant.run_workflow("qa-pipeline", "Question", stream=True):
    print(chunk.text, end="")
```

---

#### list_workflows

```python
def list_workflows(self) -> list[str]
```

Get list of available workflow names.

**Returns:** List of workflow names as strings

---

#### list_chats

```python
async def list_chats(
    self,
    source: str = "all",
    limit: int = 100
) -> list[ChatListItem]
```

List available chat sessions.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source` | `str` | `"all"` | `"cache"`, `"persistence"`, or `"all"` |
| `limit` | `int` | `100` | Maximum number of results |

**Returns:** List of `ChatListItem` objects

---

#### delete_chat

```python
async def delete_chat(self, chat_id: str) -> bool
```

Delete a chat session from all storage layers.

| Parameter | Type | Description |
|-----------|------|-------------|
| `chat_id` | `str` | The session ID to delete |

**Returns:** `True` if deleted successfully

---

#### health_check

```python
async def health_check(self) -> HealthResponse
```

Run health checks on all components.

**Returns:** `HealthResponse` with component status

**Example:**
```python
health = await assistant.health_check()
print(f"Status: {health.status}")
for component in health.components:
    print(f"  {component.name}: {component.status}")
```

---

#### get_chat_client

```python
def get_chat_client(self, model_name: Optional[str] = None) -> Any
```

Get chat client for a specific model or the default.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | `str` | `None` | Model name from the registry |

**Returns:** Chat client instance

**Raises:** `KeyError` if model_name not found in registry

---

#### list_models

```python
def list_models(self) -> list[str]
```

Get list of available model provider names.

**Returns:** List of registered model names

---

#### close

```python
async def close(self) -> None
```

Close resources and cleanup. Persists all active sessions before closing.

---

## Request Models

Located in `src/models/requests.py`.

### QuestionRequest

```python
from src.models.requests import QuestionRequest

class QuestionRequest(BaseModel):
    """Request to process a question."""
    question: str                    # User's question (1-32000 chars)
    chat_id: Optional[str]           # Session ID for continuity
    stream: bool = False             # Whether to stream response
    max_tokens: Optional[int]        # Max tokens in response (1-128000)
    temperature: Optional[float]     # Response temperature (0.0-2.0)
```

**Example:**
```python
request = QuestionRequest(
    question="What is the weather in Seattle?",
    chat_id="550e8400-e29b-41d4-a716-446655440000",
    stream=False
)
```

### WorkflowRequest

```python
class WorkflowRequest(BaseModel):
    """Request to execute a workflow."""
    workflow_name: str               # Name of the workflow
    message: str                     # Input message (1-32000 chars)
    stream: bool = False             # Whether to stream response
```

### ChatDeleteRequest

```python
class ChatDeleteRequest(BaseModel):
    """Request to delete a chat session."""
    chat_id: str                     # Session ID to delete
    delete_from_persistence: bool = True  # Also delete from ADLS
```

### ToolCallRequest

```python
class ToolCallRequest(BaseModel):
    """Direct tool call request (for testing/debugging)."""
    tool_name: str                   # Name of the tool
    parameters: Dict[str, Any] = {}  # Tool parameters
```

---

## Response Models

Located in `src/models/responses.py`.

### QuestionResponse

```python
from src.models.responses import QuestionResponse

class QuestionResponse(BaseModel):
    """Response for a processed question."""
    question: str                    # Original question
    response: str                    # AI assistant's response
    success: bool                    # Whether processing succeeded
    chat_id: str                     # Session ID for continuity

    # Optional metadata
    tokens_used: Optional[int]       # Total tokens used
    prompt_tokens: Optional[int]     # Tokens in prompt
    completion_tokens: Optional[int] # Tokens in completion
    tool_calls: List[str] = []       # Tools that were called
    latency_ms: Optional[float]      # Processing latency
    model: Optional[str]             # Model used
```

### StreamChunk

```python
class StreamChunk(BaseModel):
    """Streaming response chunk."""
    text: str = ""                   # Text content in this chunk
    done: bool = False               # Whether this is the final chunk
    chat_id: Optional[str]           # Session ID (in final chunk)
    tokens_used: Optional[int]       # Total tokens (final chunk only)
    tool_calls: Optional[List[str]]  # Tools called (final chunk only)
    error: Optional[str]             # Error message if failed
```

### WorkflowResponse

```python
class WorkflowResponse(BaseModel):
    """Response for a workflow execution."""
    workflow: str                    # Name of the executed workflow
    message: str                     # Original input message
    response: str                    # Combined output from workflow
    success: bool                    # Whether workflow completed
    author: Optional[str]            # Name of final responding agent
    steps: List[Dict[str, Any]] = [] # Workflow step details
    latency_ms: Optional[float]      # Total execution latency
```

### WorkflowStreamChunk

```python
class WorkflowStreamChunk(BaseModel):
    """Streaming workflow response chunk."""
    text: str = ""                   # Text content
    author: Optional[str]            # Agent that produced this text
    done: bool = False               # Whether workflow is complete
    steps: Optional[List[Dict]]      # Workflow steps (final chunk)
    error: Optional[str]             # Error message if failed
```

### HealthResponse

```python
class HealthResponse(BaseModel):
    """Health check response."""
    status: HealthStatus             # Overall health status
    timestamp: datetime              # Check timestamp
    version: str = "1.0.0"           # Service version
    components: List[ComponentHealth] # Component health details
```

### HealthStatus

```python
class HealthStatus(str, Enum):
    """Health check status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
```

### ComponentHealth

```python
class ComponentHealth(BaseModel):
    """Health status for a single component."""
    name: str                        # Component name
    status: HealthStatus             # Health status
    latency_ms: Optional[float]      # Check latency in ms
    message: Optional[str]           # Additional status message
    details: Optional[Dict]          # Additional details
```

### ChatListItem

```python
class ChatListItem(BaseModel):
    """Chat session metadata for listing."""
    chat_id: str                     # Session ID
    active: bool = False             # Currently active
    created_at: Optional[datetime]   # Creation time
    last_accessed: Optional[datetime] # Last access time
    message_count: int = 0           # Number of messages
    persisted: bool = False          # Persisted to ADLS
    source: Optional[str]            # Data source
    ttl_remaining: Optional[int]     # Seconds until cache expiry
```

### ErrorResponse

```python
class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str                       # Error message
    error_type: str = "unknown"      # Error classification
    details: Optional[Dict]          # Additional error details
    request_id: Optional[str]        # Request ID for tracing
    timestamp: datetime              # Error timestamp
```

---

## Configuration Classes

### AgentConfig

Located in `src/config/loader.py`.

```python
from src.config.loader import AgentConfig, get_config

config = get_config()  # Loads from config/agent.toml
```

Key properties:
- `azure_openai_endpoint` - Azure OpenAI endpoint URL
- `azure_openai_deployment` - Deployment name
- `azure_openai_api_version` - API version
- `tools_config_dir` - Directory for JSON tool configs
- `mcp_configs` - MCP server configurations
- `workflow_configs` - Workflow configurations
- `memory_config` - Memory configuration

### MemoryConfig

```python
from src.memory.manager import MemoryConfig, parse_memory_config

config = MemoryConfig(
    cache=CacheConfig(...),
    persistence=PersistenceConfig(...),
    summarization=SummarizationConfig(...),
)
```

### CacheConfig

```python
from src.memory.cache import CacheConfig

config = CacheConfig(
    enabled=True,
    host="your-redis.redis.cache.windows.net",
    port=6380,
    ssl=True,
    ttl=3600,
    prefix="chat:",
    database=0,
)
```

### PersistenceConfig

```python
from src.memory.persistence import PersistenceConfig

config = PersistenceConfig(
    enabled=True,
    account_name="yourstorageaccount",
    container="chat-history",
    folder="threads",
    schedule="ttl+300",
)
```

---

## Security Components

### RateLimiter

```python
from src.security.rate_limiter import RateLimiter, RateLimitConfig, RateLimitExceeded

config = RateLimitConfig(
    enabled=True,
    requests_per_minute=60,
    requests_per_hour=1000,
    tokens_per_minute=100000,
    max_concurrent_requests=10,
    per_user=True,
)

limiter = RateLimiter(config)

# Check limits
try:
    await limiter.check_limit(user_id="user123", estimated_tokens=500)
    await limiter.acquire_concurrent_slot(user_id="user123")
    # Process request...
    await limiter.record_request(user_id="user123", tokens_used=750)
finally:
    await limiter.release_concurrent_slot(user_id="user123")
```

### InputValidator

```python
from src.security.input_validator import (
    InputValidator,
    ValidationConfig,
    ValidationError,
    detect_prompt_injection,
    sanitize_input,
)

config = ValidationConfig(
    max_question_length=32000,
    block_prompt_injection=True,
    block_pii=False,
    redact_pii=True,
)

validator = InputValidator(config)

# Validate input
try:
    clean_text = validator.validate(user_input, context="question")
except ValidationError as e:
    print(f"Validation failed: {e.validation_type}")

# Quick detection
if detect_prompt_injection(user_input):
    print("Injection detected!")

# Sanitize with PII redaction
clean = sanitize_input(text, redact_pii=True)
```

---

## Memory Components

### ChatHistoryManager

```python
from src.memory.manager import ChatHistoryManager, MemoryConfig

manager = ChatHistoryManager(config)
manager.set_agent(agent)

# Get or create thread
chat_id, thread = await manager.get_or_create_thread(chat_id)

# Save thread
await manager.save_thread(chat_id, thread)

# Summarization
if await manager.needs_summarization(chat_id):
    await manager.summarize_if_needed(chat_id)

# Session stats
stats = await manager.get_session_stats(chat_id)

# List and delete
chats = await manager.list_chats(source="all", limit=100)
await manager.delete_chat(chat_id)

# Cleanup
await manager.close()
```

### RedisCache

```python
from src.memory.cache import RedisCache, CacheConfig

cache = RedisCache(config)

# Operations
await cache.set(key, data, ttl=3600)
data = await cache.get(key)
await cache.delete(key)
keys = await cache.list_keys(pattern="chat:*")
ttl = await cache.get_ttl(key)
await cache.refresh_ttl(key)
await cache.close()
```

### ADLSPersistence

```python
from src.memory.persistence import ADLSPersistence, PersistenceConfig

persistence = ADLSPersistence(config)

# Operations
await persistence.save(chat_id, data)
data = await persistence.get(chat_id)
exists = await persistence.exists(chat_id)
await persistence.delete(chat_id)
chats = await persistence.list_chats(limit=100)
await persistence.close()
```

---

## Tool Development

### Decorator Pattern

```python
from typing import Annotated
from pydantic import Field
from src.loaders.decorators import register_tool

@register_tool(name="my_tool", tags=["category"])
def my_tool(
    param1: Annotated[str, Field(description="Parameter description")],
    param2: Annotated[int, Field(description="Count", ge=1, le=100)] = 10,
) -> str:
    """Tool docstring becomes LLM's understanding."""
    return f"Result: {param1}"
```

### Registry Functions

```python
from src.loaders.decorators import (
    register_tool,
    get_registered_tools,
    get_tool_metadata,
    get_tools_by_tag,
    clear_registry,
)

# Get all registered tools
tools = get_registered_tools()

# Get metadata for a tool
metadata = get_tool_metadata("my_tool")

# Filter by tag
data_tools = get_tools_by_tag("data")

# Clear registry (for testing)
clear_registry()
```

---

## Observability

### Tracing

```python
from src.observability.tracing import (
    setup_tracing,
    TracingConfig,
    get_tracer,
    trace_async,
    trace_sync,
    trace_llm_call,
    trace_tool_execution,
)

# Setup
config = TracingConfig(
    enabled=True,
    service_name="ai-assistant",
    exporter_type="otlp",  # or "console", "azure", "jaeger"
)
setup_tracing(config)

# Decorators
@trace_async("process_data", {"component": "processor"})
async def process_data(data: str) -> str:
    return data.upper()

# Context managers
with trace_llm_call("gpt-4o", prompt_tokens=100) as span:
    result = await llm.complete(prompt)
    span.set_attribute("completion_tokens", result.usage.completion_tokens)
```

### Metrics

```python
from src.observability.metrics import (
    setup_metrics,
    MetricsConfig,
    get_metrics,
)

# Setup
config = MetricsConfig(
    enabled=True,
    service_name="ai-assistant",
    exporter_type="prometheus",
)
setup_metrics(config)

# Record metrics
metrics = get_metrics()
metrics.record_request(latency_ms=150.5, success=True, chat_id="abc123")
metrics.record_tool_call(tool_name="weather", latency_ms=45.2, success=True)
metrics.record_error(error_type="ValidationError", component="input_validator")
metrics.record_cache_access(hit=True, cache_type="redis")
metrics.record_tokens(prompt_tokens=100, completion_tokens=250, model="gpt-4o")

# Latency measurement
with metrics.measure_latency("tool_call") as measurement:
    result = await tool.run(args)

# Get stats
stats = metrics.get_stats()
```

---

## Model Registry

### ModelRegistry

```python
from src.models.providers import ModelRegistry, ModelProviderConfig, ModelFactory

registry = ModelRegistry()

# Register models
config = ModelProviderConfig(
    name="gpt-4o",
    provider="azure_openai",
    model="gpt-4o",
    endpoint="https://...",
)
registry.register(config, is_default=True)

# Get providers
client = ModelFactory.create_client(registry.get_default())
client = ModelFactory.create_client(registry.get_provider("gpt-4o-mini"))

# List providers
providers = registry.list_providers()
default = registry.default_name
```

### Supported Providers

| Provider | Config Fields |
|----------|---------------|
| `azure_openai` | `endpoint`, `deployment`, `api_version` |
| `openai` | `model`, API key from `OPENAI_API_KEY` |
| `anthropic` | `model`, API key from `ANTHROPIC_API_KEY` |
| `gemini` | `model`, API key from `GOOGLE_API_KEY` |
