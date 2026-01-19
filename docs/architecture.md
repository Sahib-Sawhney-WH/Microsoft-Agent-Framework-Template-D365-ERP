# MSFT Agent Framework Architecture

Detailed architectural documentation for the Microsoft Agent Framework template.

## System Overview

```mermaid
graph TB
    subgraph "User Interface"
        U[User Query + chat_id?]
    end

    subgraph "AIAssistant"
        A[Agent<br/>agent/assistant.py]
        SEC[Security<br/>security/]
        OBS[Observability<br/>observability/]
        HLT[Health<br/>health.py]
    end

    subgraph "Configuration"
        C[Config Loader<br/>config/loader.py]
        MR[Model Registry<br/>models/providers.py]
    end

    subgraph "Middleware Pipeline"
        M1[Function Call MW]
        M2[Security MW]
    end

    subgraph "Memory Layer"
        HM[History Manager<br/>memory/manager.py]
        RC[(Redis Cache)]
        AP[(ADLS Persistence)]
    end

    subgraph "Tool Loading"
        TL[Hybrid Tool Loader<br/>loaders/tools.py]
        DEC[Decorator Tools<br/>@register_tool]
        JSON[JSON Tools<br/>config/tools/*.json]
    end

    subgraph "External Integration"
        MCP[MCP Manager<br/>loaders/mcp.py]
        WF[Workflow Manager<br/>loaders/workflows.py]
    end

    subgraph "LLM Providers"
        AO[Azure OpenAI]
        OAI[OpenAI]
        CUSTOM[Custom Providers]
    end

    U --> A
    A --> SEC
    A --> OBS
    A --> HLT
    A --> C
    C --> MR
    A --> M1 --> M2
    A --> HM
    HM --> RC
    HM --> AP
    A --> TL
    TL --> DEC
    TL --> JSON
    A --> MCP
    A --> WF
    MR --> AO
    MR --> OAI
    MR --> CUSTOM
```

## Core Components

| Component | File | Responsibility |
|-----------|------|----------------|
| **AIAssistant** | `agent/assistant.py` | Main orchestrator, question processing, lifecycle |
| **AgentConfig** | `config/loader.py` | TOML loading, validation, environment overrides |
| **ModelRegistry** | `models/providers.py` | Multi-model provider management |
| **ToolLoader** | `loaders/tools.py` | Hybrid tool discovery (decorator + JSON) |
| **MCPManager** | `loaders/mcp.py` | MCP server connections (stdio/http/ws) |
| **WorkflowManager** | `loaders/workflows.py` | Multi-agent workflow orchestration |
| **ChatHistoryManager** | `memory/manager.py` | Session management, cache + persistence |
| **RedisCache** | `memory/cache.py` | Azure Cache for Redis with AAD auth |
| **ADLSPersistence** | `memory/persistence.py` | ADLS Gen2 long-term storage |
| **InputValidator** | `security/input_validator.py` | Prompt injection, PII detection |
| **RateLimiter** | `security/rate_limiter.py` | Request and token rate limiting |
| **HealthChecker** | `health.py` | Component health monitoring |
| **TracingConfig** | `observability/tracing.py` | OpenTelemetry distributed tracing |
| **MetricsCollector** | `observability/metrics.py` | Request/tool/error metrics |

## Request Flow

```mermaid
sequenceDiagram
    participant User
    participant AIAssistant
    participant RateLimiter
    participant InputValidator
    participant HistoryManager
    participant ChatAgent
    participant Tools
    participant Metrics

    User->>AIAssistant: process_question(question, chat_id)

    AIAssistant->>RateLimiter: check_limit(user_id)
    RateLimiter-->>AIAssistant: OK / RateLimitExceeded

    AIAssistant->>InputValidator: validate(question)
    InputValidator-->>AIAssistant: validated_question / ValidationError

    AIAssistant->>HistoryManager: get_or_create_thread(chat_id)
    HistoryManager-->>AIAssistant: (chat_id, thread)

    AIAssistant->>ChatAgent: run(question, thread)

    loop Agentic Loop
        ChatAgent->>ChatAgent: Reason about question
        ChatAgent->>Tools: Call tool if needed
        Tools-->>ChatAgent: Tool result
    end

    ChatAgent-->>AIAssistant: Response

    AIAssistant->>HistoryManager: save_thread(chat_id, thread)
    AIAssistant->>Metrics: record_request(latency, success)
    AIAssistant-->>User: QuestionResponse
```

## Tool Loading Architecture

The framework supports hybrid tool loading with decorator tools taking precedence.

```mermaid
graph TB
    subgraph "Configuration"
        TOML[agent.toml<br/>tool_modules list]
        JSOND[config/tools/*.json<br/>Tool definitions]
    end

    subgraph "Decorator Discovery"
        MODS[Import Modules]
        SCAN[@register_tool scan]
        REG[Tool Registry]
    end

    subgraph "JSON Discovery"
        JSONL[Load JSON files]
        SVC[Find service.py]
        CLASS[Find Service class]
    end

    subgraph "Merge & Register"
        MERGE[Merge tools<br/>Decorators win conflicts]
        BIND[Bind to ChatAgent]
    end

    TOML --> MODS
    MODS --> SCAN
    SCAN --> REG
    JSOND --> JSONL
    JSONL --> SVC
    SVC --> CLASS
    REG --> MERGE
    CLASS --> MERGE
    MERGE --> BIND

    style SCAN fill:#e8f5e9
    style MERGE fill:#fff3e0
```

### Decorator Pattern (Recommended)

```python
from src.tools import ai_function, register_tool, Annotated, Field

@register_tool(name="my_tool", tags=["utilities"])
@ai_function
def my_tool(
    param: Annotated[str, Field(description="Parameter description")],
) -> str:
    """Tool docstring becomes LLM's understanding."""
    return f"Result: {param}"
```

### JSON + Service Pattern (Legacy)

```
config/tools/weather.json  →  src/weather/service.py  →  WeatherService.run()
```

## Multi-Model Architecture

```mermaid
graph TB
    subgraph "Configuration"
        TOML["[[agent.models]]<br/>in agent.toml"]
    end

    subgraph "Model Registry"
        REG[ModelRegistry]
        CFG1[azure_openai config]
        CFG2[openai config]
        CFG3[custom config]
    end

    subgraph "Model Factory"
        FAC[ModelFactory.create_client]
    end

    subgraph "Providers"
        AO[AzureChatCompletionClient]
        OAI[ChatCompletionClient]
        CUSTOM[Custom Client]
    end

    TOML --> REG
    REG --> CFG1
    REG --> CFG2
    REG --> CFG3
    CFG1 --> FAC
    CFG2 --> FAC
    CFG3 --> FAC
    FAC --> AO
    FAC --> OAI
    FAC --> CUSTOM
```

**Configuration:**

```toml
[[agent.models]]
name = "gpt-4o"
provider = "azure_openai"
model = "gpt-4o"
endpoint = "https://your-resource.openai.azure.com/"
default = true

[[agent.models]]
name = "gpt-4o-mini"
provider = "azure_openai"
model = "gpt-4o-mini"
```

**Usage:**

```python
# Use default model
result = await assistant.process_question("Hello")

# Use specific model
result = await assistant.process_question("Hello", model="gpt-4o-mini")

# Get client directly
client = assistant.get_chat_client("gpt-4o-mini")
```

## Memory & Session Management

```mermaid
flowchart TB
    subgraph "Request"
        Q[Question + chat_id?]
    end

    subgraph "ChatHistoryManager"
        CHK{chat_id<br/>provided?}
        CACHE[Check Redis]
        ADLS[Check ADLS]
        NEW[Create Thread]
        RESTORE[Restore Thread]
        SUMM{Needs<br/>summarization?}
        SUM[Summarize]
    end

    subgraph "Storage"
        RC[(Redis Cache<br/>TTL: 1 hour)]
        AP[(ADLS Gen2<br/>Persistent)]
    end

    Q --> CHK
    CHK -->|No| NEW
    CHK -->|Yes| CACHE
    CACHE -->|Hit| RESTORE
    CACHE -->|Miss| ADLS
    ADLS -->|Found| RESTORE
    ADLS -->|Not Found| NEW
    RESTORE --> SUMM
    SUMM -->|Yes| SUM
    SUM --> RC
    SUMM -->|No| RC
    NEW --> RC
    RC -.->|Before TTL expiry| AP
```

**Session Flow:**

| chat_id | Cache | ADLS | Action |
|---------|-------|------|--------|
| None | - | - | Generate UUID, create thread |
| Provided | Hit | - | Restore from cache |
| Provided | Miss | Found | Load from ADLS, cache it |
| Provided | Miss | Not Found | Create new with provided ID |

See [memory.md](memory.md) for detailed configuration.

## MCP Integration

```mermaid
graph TB
    subgraph "Configuration"
        TOML["[[agent.mcp]]<br/>in agent.toml"]
    end

    subgraph "MCPManager"
        PARSE[Parse configs]
        CREATE[Create tools]
    end

    subgraph "Transport Types"
        STDIO[MCPStdioTool<br/>Local subprocess]
        HTTP[MCPStreamableHTTPTool<br/>REST + SSE]
        WS[MCPWebsocketTool<br/>WebSocket]
    end

    subgraph "Session Management"
        SESS[MCPSessionManager]
        STATE[Stateful sessions<br/>per chat_id]
    end

    subgraph "External Servers"
        CALC[mcp-server-calculator]
        FS[mcp-server-filesystem]
        CUSTOM[Custom servers]
    end

    TOML --> PARSE
    PARSE --> CREATE
    CREATE --> STDIO
    CREATE --> HTTP
    CREATE --> WS
    STDIO --> CALC
    STDIO --> FS
    HTTP --> CUSTOM
    WS --> CUSTOM
    CREATE --> SESS
    SESS --> STATE
```

## Workflow Architecture

```mermaid
graph TB
    subgraph "Configuration"
        WF_TOML["[[agent.workflows]]<br/>in agent.toml"]
    end

    subgraph "WorkflowManager"
        PARSE[Parse configs]
        BUILD[Build agents]
    end

    subgraph "Workflow Types"
        SEQ[Sequential<br/>Linear pipeline]
        CUSTOM[Custom<br/>Graph-based]
    end

    subgraph "Execution"
        A1[Agent 1]
        A2[Agent 2]
        A3[Agent 3]
    end

    WF_TOML --> PARSE
    PARSE --> BUILD
    BUILD --> SEQ
    BUILD --> CUSTOM
    SEQ --> A1 --> A2 --> A3
    CUSTOM --> A1
    A1 -.-> A2
    A1 -.-> A3
```

**Sequential Workflow:**

```mermaid
graph LR
    INPUT[User Input] --> R[Researcher]
    R --> W[Writer]
    W --> REV[Reviewer]
    REV --> OUTPUT[Final Response]

    style R fill:#e1f5fe
    style W fill:#fff3e0
    style REV fill:#e8f5e9
```

## Observability Architecture

```mermaid
graph TB
    subgraph "Application"
        REQ[Request Handler]
        TOOL[Tool Execution]
        LLM[LLM Call]
    end

    subgraph "Tracing"
        TRACER[OpenTelemetry Tracer]
        SPAN1[process_question span]
        SPAN2[tool_execution span]
        SPAN3[llm_call span]
    end

    subgraph "Metrics"
        MC[MetricsCollector]
        CNT[Counters<br/>requests, errors]
        HIST[Histograms<br/>latency]
        GAUGE[Gauges<br/>active sessions]
    end

    subgraph "Exporters"
        CONSOLE[Console]
        OTLP[OTLP Collector]
        AZURE[Azure Monitor]
        PROM[Prometheus]
    end

    REQ --> SPAN1
    TOOL --> SPAN2
    LLM --> SPAN3
    SPAN1 --> TRACER
    SPAN2 --> TRACER
    SPAN3 --> TRACER

    REQ --> MC
    TOOL --> MC
    MC --> CNT
    MC --> HIST
    MC --> GAUGE

    TRACER --> CONSOLE
    TRACER --> OTLP
    TRACER --> AZURE

    MC --> CONSOLE
    MC --> PROM
    MC --> AZURE
```

See [observability.md](observability.md) for configuration details.

## Security Architecture

```mermaid
graph TB
    subgraph "Incoming Request"
        REQ[User Question]
    end

    subgraph "Rate Limiter"
        RL_CHK{Check limits}
        RL_REQ[Requests/min]
        RL_TOK[Tokens/min]
        RL_CON[Concurrent]
    end

    subgraph "Input Validator"
        IV_LEN[Length check]
        IV_INJ[Injection detection<br/>60+ patterns]
        IV_PII[PII detection]
        IV_BLK[Blocked patterns]
    end

    subgraph "Tool Validator"
        TV_WL[Tool whitelist]
        TV_BL[Tool blacklist]
        TV_PAR[Parameter validation]
    end

    subgraph "Processing"
        AGENT[ChatAgent]
    end

    REQ --> RL_CHK
    RL_CHK --> RL_REQ
    RL_CHK --> RL_TOK
    RL_CHK --> RL_CON
    RL_CHK -->|Pass| IV_LEN
    IV_LEN --> IV_INJ
    IV_INJ --> IV_PII
    IV_PII --> IV_BLK
    IV_BLK -->|Pass| AGENT
    AGENT --> TV_WL
    AGENT --> TV_BL
    AGENT --> TV_PAR

    style RL_CHK fill:#ffebee
    style IV_INJ fill:#fff3e0
    style IV_PII fill:#e3f2fd
```

See [security.md](security.md) for configuration details.

## Health Check System

```mermaid
graph TB
    subgraph "Health Endpoints"
        READY[/health/ready<br/>Readiness probe]
        LIVE[/health/live<br/>Liveness probe]
        FULL[/health<br/>Full status]
    end

    subgraph "HealthChecker"
        CHK[check_all]
        CACHE_R[Cache results<br/>10s TTL]
    end

    subgraph "Component Checks"
        C_REDIS[Redis ping]
        C_ADLS[ADLS access]
        C_MCP[MCP tools count]
        C_LLM[LLM connectivity]
    end

    subgraph "Status"
        S_OK[HEALTHY]
        S_DEG[DEGRADED]
        S_ERR[UNHEALTHY]
    end

    READY --> CHK
    LIVE --> CHK
    FULL --> CHK
    CHK --> CACHE_R
    CACHE_R --> C_REDIS
    CACHE_R --> C_ADLS
    CACHE_R --> C_MCP
    CACHE_R --> C_LLM
    C_REDIS --> S_OK
    C_REDIS --> S_DEG
    C_ADLS --> S_ERR
```

**Response Format:**

```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:30:00Z",
  "version": "1.0.0",
  "uptime_seconds": 3600.5,
  "components": [
    {"name": "redis", "status": "healthy", "latency_ms": 2.5},
    {"name": "adls", "status": "healthy", "latency_ms": 45.2},
    {"name": "mcp", "status": "healthy", "latency_ms": 0.1, "details": {"tool_count": 5}}
  ]
}
```

## Data Flow Summary

1. **User Query** → AIAssistant receives question + optional `chat_id`
2. **Rate Limiting** → Check request/token limits
3. **Input Validation** → Detect injection, PII, blocked content
4. **Session Lookup** → ChatHistoryManager: cache → ADLS → create new
5. **Configuration** → Load TOML, environment overrides
6. **Tool Loading** → Decorator tools + JSON tools (hybrid)
7. **MCP Loading** → Connect to external MCP servers
8. **Workflow Loading** → Build multi-agent pipelines
9. **Agent Creation** → Initialize ChatAgent with tools + middleware
10. **Processing** → LLM reasons and calls tools as needed
11. **Summarization** → Compress context if token limit exceeded
12. **Session Save** → Update cache, persist to ADLS before TTL
13. **Metrics** → Record latency, success, tool calls
14. **Response** → Final answer + `chat_id` returned to user
