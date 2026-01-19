# API Reference

Complete API reference for the MSFT Agent Framework.

## AIAssistant

The main class for interacting with the AI agent.

### Import

```python
from src.agent import AIAssistant
```

### Constructor

```python
AIAssistant(
    config_path: str | None = None,
    config: AgentConfig | None = None
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config_path` | `str \| None` | `None` | Path to configuration file. If `None`, uses `config/agent.toml` |
| `config` | `AgentConfig \| None` | `None` | Pre-loaded configuration object |

**Example:**

```python
# Default configuration
assistant = AIAssistant()

# Custom config path
assistant = AIAssistant(config_path="custom/agent.toml")

# Pre-loaded config
from src.config import load_config
config = load_config("custom/agent.toml")
assistant = AIAssistant(config=config)
```

---

### Context Manager

AIAssistant should be used as an async context manager:

```python
async with AIAssistant() as assistant:
    result = await assistant.process_question("Hello!")
```

The context manager handles:
- Initializing connections (OpenAI, Redis, ADLS, MCP)
- Registering health checks
- Cleaning up resources on exit

---

### Methods

#### `process_question`

Process a single question and return a complete response.

```python
async def process_question(
    question: str,
    chat_id: str | None = None,
    user_id: str | None = None,
    metadata: dict | None = None
) -> QuestionResponse
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `question` | `str` | Required | The user's question or message |
| `chat_id` | `str \| None` | `None` | Session ID for conversation continuity. If `None`, creates new session |
| `user_id` | `str \| None` | `None` | User identifier for tracking/personalization |
| `metadata` | `dict \| None` | `None` | Additional metadata to attach to the request |

**Returns:** `QuestionResponse`

**Example:**

```python
async with AIAssistant() as assistant:
    # New conversation
    result = await assistant.process_question("Hello!")
    print(result.response)
    print(result.chat_id)  # Save for continuation

    # Continue conversation
    result2 = await assistant.process_question(
        "What did I just say?",
        chat_id=result.chat_id
    )
```

---

#### `process_question_stream`

Process a question and stream the response in chunks.

```python
async def process_question_stream(
    question: str,
    chat_id: str | None = None,
    user_id: str | None = None,
    metadata: dict | None = None
) -> AsyncIterator[StreamChunk]
```

**Parameters:** Same as `process_question`

**Returns:** `AsyncIterator[StreamChunk]`

**Example:**

```python
async with AIAssistant() as assistant:
    async for chunk in await assistant.process_question_stream("Tell me a story"):
        print(chunk.text, end="", flush=True)
    print()  # Newline at end
```

---

#### `run_workflow`

Execute a multi-agent workflow.

```python
async def run_workflow(
    workflow_name: str,
    input_text: str,
    chat_id: str | None = None,
    user_id: str | None = None
) -> WorkflowResponse
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `workflow_name` | `str` | Required | Name of workflow (from configuration) |
| `input_text` | `str` | Required | Input for the workflow |
| `chat_id` | `str \| None` | `None` | Session ID |
| `user_id` | `str \| None` | `None` | User identifier |

**Returns:** `WorkflowResponse`

**Example:**

```python
async with AIAssistant() as assistant:
    result = await assistant.run_workflow(
        "content-pipeline",
        "Write about artificial intelligence trends"
    )
    print(result.response)
    for step in result.steps:
        print(f"  {step.agent}: {step.output[:100]}...")
```

---

#### `health_check`

Check the health of all components.

```python
async def health_check() -> HealthCheckResult
```

**Returns:** `HealthCheckResult`

**Example:**

```python
async with AIAssistant() as assistant:
    health = await assistant.health_check()
    print(f"Status: {health.status}")
    print(f"Uptime: {health.uptime_seconds}s")
    for component in health.components:
        print(f"  {component.name}: {component.status} ({component.latency_ms}ms)")
```

---

#### `get_tools`

Get list of available tools.

```python
def get_tools() -> list[ToolDefinition]
```

**Returns:** List of `ToolDefinition` objects

**Example:**

```python
async with AIAssistant() as assistant:
    tools = assistant.get_tools()
    for tool in tools:
        print(f"{tool.name}: {tool.description}")
```

---

## Response Models

### QuestionResponse

Response from `process_question`.

```python
@dataclass
class QuestionResponse:
    response: str           # The assistant's response text
    chat_id: str           # Session ID for continuation
    tokens_used: int       # Total tokens used
    model: str             # Model used for response
    tools_called: list[str] # Names of tools invoked
    metadata: dict         # Additional metadata
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `response` | `str` | The assistant's response text |
| `chat_id` | `str` | Session ID (use for conversation continuation) |
| `tokens_used` | `int` | Total tokens consumed |
| `model` | `str` | Model name used |
| `tools_called` | `list[str]` | Tools that were invoked |
| `metadata` | `dict` | Additional response metadata |

---

### StreamChunk

Chunk from `process_question_stream`.

```python
@dataclass
class StreamChunk:
    text: str              # Text content of this chunk
    is_final: bool         # True if this is the last chunk
    tool_call: str | None  # Tool being called (if any)
    metadata: dict         # Chunk metadata
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Text content of this chunk |
| `is_final` | `bool` | `True` if this is the last chunk |
| `tool_call` | `str \| None` | Name of tool being called (during tool execution) |
| `metadata` | `dict` | Additional chunk metadata |

---

### WorkflowResponse

Response from `run_workflow`.

```python
@dataclass
class WorkflowResponse:
    response: str           # Final workflow output
    chat_id: str           # Session ID
    workflow_name: str     # Name of executed workflow
    steps: list[WorkflowStep]  # Individual agent outputs
    total_tokens: int      # Total tokens across all agents
    metadata: dict         # Workflow metadata
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `response` | `str` | Final output from last agent |
| `chat_id` | `str` | Session ID |
| `workflow_name` | `str` | Name of the workflow |
| `steps` | `list[WorkflowStep]` | Output from each agent |
| `total_tokens` | `int` | Tokens used by all agents |
| `metadata` | `dict` | Additional metadata |

### WorkflowStep

Individual step in a workflow.

```python
@dataclass
class WorkflowStep:
    agent: str             # Agent name
    output: str            # Agent's output
    tokens_used: int       # Tokens for this step
    model: str             # Model used
```

---

### HealthCheckResult

Response from `health_check`.

```python
@dataclass
class HealthCheckResult:
    status: HealthStatus   # Overall status
    timestamp: datetime    # Check timestamp
    version: str           # Framework version
    components: list[ComponentCheck]  # Individual checks
    uptime_seconds: float  # Service uptime
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `status` | `HealthStatus` | Overall status: `healthy`, `degraded`, `unhealthy` |
| `timestamp` | `datetime` | When check was performed |
| `version` | `str` | Framework version |
| `components` | `list[ComponentCheck]` | Per-component results |
| `uptime_seconds` | `float` | Seconds since startup |

### ComponentCheck

Individual component health.

```python
@dataclass
class ComponentCheck:
    name: str              # Component name
    status: HealthStatus   # Component status
    latency_ms: float      # Check latency
    message: str | None    # Status message
    details: dict | None   # Additional details
```

### HealthStatus

Health status enumeration.

```python
class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
```

---

## Tool Definition

### ToolDefinition

```python
@dataclass
class ToolDefinition:
    name: str              # Tool name
    description: str       # Tool description
    parameters: dict       # JSON Schema for parameters
    tags: list[str]        # Tool tags/categories
```

---

## Error Handling

### Common Exceptions

| Exception | Description |
|-----------|-------------|
| `ConfigurationError` | Invalid configuration |
| `AuthenticationError` | Azure authentication failed |
| `RateLimitError` | Rate limit exceeded |
| `ToolExecutionError` | Tool failed to execute |
| `MCPConnectionError` | MCP server connection failed |

**Example:**

```python
from src.agent import AIAssistant
from src.exceptions import RateLimitError, ToolExecutionError

async with AIAssistant() as assistant:
    try:
        result = await assistant.process_question("Hello!")
    except RateLimitError as e:
        print(f"Rate limited, retry after {e.retry_after}s")
    except ToolExecutionError as e:
        print(f"Tool {e.tool_name} failed: {e.message}")
```

---

## Usage Patterns

### Basic Usage

```python
import asyncio
from src.agent import AIAssistant

async def main():
    async with AIAssistant() as assistant:
        result = await assistant.process_question("What's 2+2?")
        print(result.response)

asyncio.run(main())
```

### Conversation with History

```python
async def conversation():
    async with AIAssistant() as assistant:
        # Start conversation
        r1 = await assistant.process_question("My name is Alice")
        chat_id = r1.chat_id

        # Continue with context
        r2 = await assistant.process_question("What's my name?", chat_id=chat_id)
        # r2.response will reference "Alice"

        r3 = await assistant.process_question("Tell me a joke", chat_id=chat_id)
        # Full conversation history maintained
```

### Streaming with Progress

```python
async def stream_with_progress():
    async with AIAssistant() as assistant:
        print("Assistant: ", end="")
        async for chunk in await assistant.process_question_stream("Explain AI"):
            if chunk.tool_call:
                print(f"\n[Calling tool: {chunk.tool_call}]")
            else:
                print(chunk.text, end="", flush=True)
        print()
```

### Workflow Execution

```python
async def run_content_pipeline():
    async with AIAssistant() as assistant:
        result = await assistant.run_workflow(
            "content-pipeline",
            "Write about machine learning"
        )

        print("=== Workflow Steps ===")
        for step in result.steps:
            print(f"\n{step.agent} ({step.tokens_used} tokens):")
            print(step.output[:200] + "...")

        print("\n=== Final Output ===")
        print(result.response)
```

### Health Monitoring

```python
async def monitor_health():
    async with AIAssistant() as assistant:
        while True:
            health = await assistant.health_check()
            if health.status != "healthy":
                print(f"ALERT: Status is {health.status}")
                for c in health.components:
                    if c.status != "healthy":
                        print(f"  - {c.name}: {c.message}")
            await asyncio.sleep(30)
```

---

## Related Documentation

- [Quickstart](../getting-started/quickstart.md) — Get started quickly
- [Tools Guide](../tools.md) — Creating custom tools
- [Architecture](../architecture.md) — System design

---
*Last updated: 2026-01-17*
