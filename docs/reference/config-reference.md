# Configuration Reference

Complete reference for `agent.toml` configuration options.

## File Location

Configuration is loaded from `config/agent.toml` relative to the project root.

---

## `[agent]`

Core agent settings.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `system_prompt` | string | `"config/system_prompt.txt"` | Path to system prompt file |
| `log_level` | string | `"INFO"` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `default_model` | string | Required | Name of default model (must match `[[agent.models]].name`) |

**Example:**

```toml
[agent]
system_prompt = "config/system_prompt.txt"
log_level = "INFO"
default_model = "azure_openai"
```

---

## `[[agent.models]]`

Model provider configurations. Multiple providers can be defined.

### Common Fields

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | Yes | Unique identifier for this model |
| `provider` | string | Yes | Provider type: `azure_openai`, `openai`, `anthropic`, `gemini` |

### Azure OpenAI Provider

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `endpoint` | string | Required | Azure OpenAI endpoint URL |
| `deployment` | string | Required | Model deployment name |
| `api_version` | string | `"2024-10-01-preview"` | API version |

**Example:**

```toml
[[agent.models]]
name = "azure_openai"
provider = "azure_openai"
endpoint = "https://your-resource.openai.azure.com/"
deployment = "gpt-4o"
api_version = "2024-10-01-preview"
```

### OpenAI Provider

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model` | string | Required | Model name (e.g., `gpt-4-turbo`) |

API key from `OPENAI_API_KEY` environment variable.

**Example:**

```toml
[[agent.models]]
name = "openai"
provider = "openai"
model = "gpt-4-turbo"
```

### Anthropic Provider

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model` | string | Required | Model name (e.g., `claude-3-opus-20240229`) |

API key from `ANTHROPIC_API_KEY` environment variable.

**Example:**

```toml
[[agent.models]]
name = "claude"
provider = "anthropic"
model = "claude-3-opus-20240229"
```

### Google Gemini Provider

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `model` | string | Required | Model name (e.g., `gemini-pro`) |

API key from `GOOGLE_API_KEY` environment variable.

**Example:**

```toml
[[agent.models]]
name = "gemini"
provider = "gemini"
model = "gemini-pro"
```

---

## `[agent.azure_openai]` (Legacy)

Legacy Azure OpenAI configuration. Used if `[[agent.models]]` is not configured.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `endpoint` | string | Required | Azure OpenAI endpoint URL |
| `deployment` | string | Required | Model deployment name |
| `api_version` | string | `"2024-10-01-preview"` | API version |

**Example:**

```toml
[agent.azure_openai]
endpoint = "https://your-resource.openai.azure.com/"
deployment = "gpt-4o"
api_version = "2024-10-01-preview"
```

---

## `[agent.tools]`

Tool loading configuration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `config_dir` | string | `"config/tools"` | Directory for JSON tool definitions |
| `tool_modules` | array | `[]` | Python modules to load tools from |

**Example:**

```toml
[agent.tools]
config_dir = "config/tools"
tool_modules = ["src.example_tool.tools", "src.my_tools"]
```

### Tool-Specific Configuration

Configure individual tools with `[agent.tools.<tool_name>]`:

```toml
[agent.tools.my_tool]
api_base_url = "https://api.example.com"
timeout = 30
max_retries = 3
```

---

## `[[agent.mcp]]`

MCP (Model Context Protocol) server configurations.

### Common Fields

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | Yes | Unique identifier for this MCP server |
| `type` | string | Yes | Server type: `stdio`, `http`, `websocket`, `d365` |
| `enabled` | boolean | `true` | Enable/disable this server |
| `description` | string | `""` | Human-readable description |

### Stdio MCP Server

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `command` | string | Yes | Command to run |
| `args` | array | `[]` | Command arguments |
| `env` | table | `{}` | Environment variables for subprocess |

**Example:**

```toml
[[agent.mcp]]
name = "calculator"
type = "stdio"
enabled = true
command = "uvx"
args = ["mcp-server-calculator"]
env = { DEBUG = "true" }
```

### HTTP MCP Server

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `url` | string | Yes | Server URL |
| `headers` | table | `{}` | HTTP headers |
| `timeout` | integer | `30` | Request timeout in seconds |

**Example:**

```toml
[[agent.mcp]]
name = "my-api"
type = "http"
enabled = true
url = "https://api.example.com/mcp"
headers = { Authorization = "Bearer token" }
timeout = 60
```

### WebSocket MCP Server

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `url` | string | Yes | WebSocket URL |
| `headers` | table | `{}` | Connection headers |

**Example:**

```toml
[[agent.mcp]]
name = "realtime"
type = "websocket"
enabled = true
url = "wss://api.example.com/mcp"
headers = { Authorization = "Bearer token" }
```

### D365 MCP Server

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `timeout` | integer | `60` | HTTP timeout in seconds |

OAuth configuration under `[agent.mcp.oauth]`:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `environment_url` | string | Yes | D365 environment URL |
| `tenant_id` | string | No | Azure AD tenant ID |
| `client_id` | string | No | Application client ID |
| `client_secret` | string | No | Client secret (supports `${ENV_VAR}`) |

**Example:**

```toml
[[agent.mcp]]
name = "d365-fo"
type = "d365"
enabled = true
description = "D365 Finance & Operations"
timeout = 60

[agent.mcp.oauth]
environment_url = "https://myorg.operations.dynamics.com"
tenant_id = "your-tenant-id"
client_id = "your-client-id"
client_secret = "${D365_CLIENT_SECRET}"
```

### Stateful MCP Server (Legacy)

Additional fields for stateful HTTP servers:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `stateful` | boolean | `false` | Enable session handling |
| `session_header` | string | `"X-Session-Id"` | Header for session ID |
| `form_context_header` | string | `""` | Header for form state |
| `requires_user_id` | boolean | `false` | Require user ID for sessions |

---

## `[agent.mcp_sessions]`

Session management for stateful MCP servers.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `false` | Enable session management |
| `session_ttl` | integer | `3600` | Session TTL in seconds |
| `persist_sessions` | boolean | `true` | Persist sessions to ADLS |

**Example:**

```toml
[agent.mcp_sessions]
enabled = true
session_ttl = 3600
persist_sessions = true
```

---

## `[[agent.workflows]]`

Multi-agent workflow configurations.

### Common Fields

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | Yes | Unique workflow identifier |
| `type` | string | Yes | Workflow type: `sequential`, `custom` |
| `enabled` | boolean | `true` | Enable/disable workflow |

### Sequential Workflow

Agents execute in order, each agent's output becomes the next agent's input.

**Example:**

```toml
[[agent.workflows]]
name = "content-pipeline"
type = "sequential"
enabled = true

[[agent.workflows.agents]]
name = "Researcher"
instructions = "Research the topic."

[[agent.workflows.agents]]
name = "Writer"
instructions = "Write content based on research."
```

### Custom Workflow

Agents connected by explicit edges.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `start` | string | Yes | Name of starting agent |

**Example:**

```toml
[[agent.workflows]]
name = "support-flow"
type = "custom"
enabled = true
start = "Triage"

[[agent.workflows.agents]]
name = "Triage"
instructions = "Analyze the issue."

[[agent.workflows.agents]]
name = "TechSupport"
instructions = "Provide technical solutions."

[[agent.workflows.edges]]
from = "Triage"
to = "TechSupport"
```

### Agent Configuration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | Required | Agent identifier |
| `instructions` | string | Required | Agent system instructions |
| `model` | string | Default model | Override model for this agent |

---

## `[agent.memory.cache]`

Redis cache configuration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable Redis caching |
| `host` | string | Required | Redis host |
| `port` | integer | `6380` | Redis port |
| `ssl` | boolean | `true` | Use SSL/TLS |
| `ttl` | integer | `300` | Cache TTL in seconds |
| `prefix` | string | `"chat:"` | Key prefix |
| `database` | integer | `0` | Redis database number |

**Example:**

```toml
[agent.memory.cache]
enabled = true
host = "your-redis.redis.cache.windows.net"
port = 6380
ssl = true
ttl = 300
prefix = "chat:"
database = 0
```

---

## `[agent.memory.persistence]`

Azure Blob Storage persistence configuration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable ADLS persistence |
| `account_name` | string | Required | Storage account name |
| `container` | string | Required | Container name |
| `folder` | string | `"threads"` | Folder within container |
| `schedule` | string | `"ttl+60"` | When to persist (ttl+N = N seconds after cache TTL) |

**Example:**

```toml
[agent.memory.persistence]
enabled = true
account_name = "yourstorageaccount"
container = "chat-history"
folder = "threads"
schedule = "ttl+60"
```

---

## `[agent.memory.summarization]`

Auto-summarization configuration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `false` | Enable auto-summarization |
| `max_tokens` | integer | `4000` | Trigger summarization above this |
| `target_tokens` | integer | `2000` | Target size after summarization |

**Example:**

```toml
[agent.memory.summarization]
enabled = true
max_tokens = 4000
target_tokens = 2000
```

---

## `[agent.security]`

Security configuration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `require_authentication` | boolean | `false` | Require auth for API |
| `allowed_origins` | array | `["*"]` | CORS allowed origins |

**Example:**

```toml
[agent.security]
require_authentication = true
allowed_origins = ["https://myapp.com", "https://admin.myapp.com"]
```

### `[agent.security.rate_limiting]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable rate limiting |
| `requests_per_minute` | integer | `60` | Max requests per minute |
| `burst_limit` | integer | `10` | Burst allowance |

### `[agent.security.input_validation]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable input validation |
| `max_input_length` | integer | `10000` | Maximum input characters |

### `[agent.security.pii_detection]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `false` | Enable PII detection |
| `action` | string | `"warn"` | Action: `warn`, `block`, `redact` |

---

## Variable Substitution

Environment variables can be referenced in string values:

```toml
client_secret = "${D365_CLIENT_SECRET}"
```

At runtime, `${D365_CLIENT_SECRET}` is replaced with the environment variable value.

---

## Related Documentation

- [Configuration Guide](../getting-started/configuration.md) — Getting started with configuration
- [Environment Variables](environment-variables.md) — All environment variables
- [Security](../security.md) — Security features

---
*Last updated: 2026-01-17*
