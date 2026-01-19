# Configuration

This guide covers configuring the MSFT Agent Framework for your needs.

## Overview

The framework uses TOML configuration files with environment variable overrides. Configuration is loaded from:

1. `config/agent.toml` — Primary configuration file
2. Environment variables — Override specific settings
3. Defaults — Built-in fallback values

## Quick Setup

Copy and edit the example configuration:

```bash
cp config/agent.toml.example config/agent.toml
```

Minimal configuration:

```toml
[agent]
system_prompt = "config/system_prompt.txt"
log_level = "INFO"
default_model = "azure_openai"

[[agent.models]]
name = "azure_openai"
provider = "azure_openai"
endpoint = "https://your-resource.openai.azure.com/"
deployment = "gpt-4o"
api_version = "2024-10-01-preview"
```

## Configuration Sections

### Core Settings (`[agent]`)

```toml
[agent]
# Path to system prompt file
system_prompt = "config/system_prompt.txt"

# Logging level: DEBUG, INFO, WARNING, ERROR
log_level = "INFO"

# Default model to use (must match a name from [[agent.models]])
default_model = "azure_openai"
```

### Model Providers (`[[agent.models]]`)

Configure one or more LLM providers:

#### Azure OpenAI

```toml
[[agent.models]]
name = "azure_openai"
provider = "azure_openai"
endpoint = "https://your-resource.openai.azure.com/"
deployment = "gpt-4o"
api_version = "2024-10-01-preview"
```

#### OpenAI Direct

```toml
[[agent.models]]
name = "openai"
provider = "openai"
model = "gpt-4-turbo"
# API key from OPENAI_API_KEY environment variable
```

#### Anthropic Claude

```toml
[[agent.models]]
name = "claude"
provider = "anthropic"
model = "claude-3-opus-20240229"
# API key from ANTHROPIC_API_KEY environment variable
```

#### Google Gemini

```toml
[[agent.models]]
name = "gemini"
provider = "gemini"
model = "gemini-pro"
# API key from GOOGLE_API_KEY environment variable
```

### Legacy Azure OpenAI (`[agent.azure_openai]`)

For backward compatibility, you can use the legacy format:

```toml
[agent.azure_openai]
endpoint = "https://your-resource.openai.azure.com/"
deployment = "gpt-4o"
api_version = "2024-10-01-preview"
```

Note: `[[agent.models]]` takes precedence if configured.

### Tool Configuration (`[agent.tools]`)

```toml
[agent.tools]
# Directory containing JSON tool definitions
config_dir = "config/tools"

# Python modules to load tools from
tool_modules = ["src.example_tool.tools", "src.my_tools"]

# Tool-specific settings
[agent.tools.my_tool]
api_base_url = "https://api.example.com"
timeout = 30
max_retries = 3
```

### MCP Servers (`[[agent.mcp]]`)

Connect to external MCP (Model Context Protocol) servers:

#### Stdio MCP Server

```toml
[[agent.mcp]]
name = "calculator"
type = "stdio"
enabled = true
command = "uvx"
args = ["mcp-server-calculator"]
# Optional: environment variables for the subprocess
# env = { API_KEY = "xxx" }
```

#### HTTP MCP Server

```toml
[[agent.mcp]]
name = "my-api"
type = "http"
enabled = true
url = "https://api.example.com/mcp"
# Optional: authentication headers
# headers = { Authorization = "Bearer your-token" }
```

#### WebSocket MCP Server

```toml
[[agent.mcp]]
name = "realtime-data"
type = "websocket"
enabled = true
url = "wss://api.example.com/mcp"
headers = { Authorization = "Bearer your-token" }
```

#### D365 MCP Server (OAuth)

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
client_secret = "${D365_CLIENT_SECRET}"  # From environment variable
```

### MCP Sessions (`[agent.mcp_sessions]`)

For stateful MCP servers:

```toml
[agent.mcp_sessions]
enabled = false              # Enable session management
session_ttl = 3600          # Session TTL in seconds
persist_sessions = true     # Persist to ADLS
```

### Workflows (`[[agent.workflows]]`)

Configure multi-agent pipelines:

#### Sequential Workflow

```toml
[[agent.workflows]]
name = "content-pipeline"
type = "sequential"
enabled = true

[[agent.workflows.agents]]
name = "Researcher"
instructions = "Research the topic and provide key facts."

[[agent.workflows.agents]]
name = "Writer"
instructions = "Write engaging content based on the research."

[[agent.workflows.agents]]
name = "Reviewer"
instructions = "Review and provide final polished version."
```

#### Multi-Model Workflow

```toml
[[agent.workflows]]
name = "research-pipeline"
type = "sequential"
enabled = true

[[agent.workflows.agents]]
name = "Researcher"
model = "openai"  # Uses OpenAI
instructions = "Research the topic using web search."

[[agent.workflows.agents]]
name = "Analyst"
model = "claude"  # Uses Anthropic Claude
instructions = "Analyze findings with critical thinking."

[[agent.workflows.agents]]
name = "Reporter"
# No model specified - uses default
instructions = "Write comprehensive final report."
```

### Memory / Cache (`[agent.memory.cache]`)

Configure Redis caching:

```toml
[agent.memory.cache]
enabled = true
host = "your-redis.redis.cache.windows.net"
port = 6380
ssl = true
ttl = 300              # Cache TTL in seconds
prefix = "chat:"       # Key prefix
database = 0
```

### Memory / Persistence (`[agent.memory.persistence]`)

Configure ADLS persistence:

```toml
[agent.memory.persistence]
enabled = true
account_name = "yourstorageaccount"
container = "chat-history"
folder = "threads"
schedule = "ttl+60"    # Persist 60 seconds after cache TTL
```

### Memory / Summarization (`[agent.memory.summarization]`)

Configure auto-summarization:

```toml
[agent.memory.summarization]
enabled = true
max_tokens = 4000      # Trigger summarization above this
target_tokens = 2000   # Target size after summarization
```

### Security (`[agent.security]`)

Configure security features:

```toml
[agent.security]
require_authentication = true
allowed_origins = ["https://your-app.com"]

[agent.security.rate_limiting]
enabled = true
requests_per_minute = 60
burst_limit = 10

[agent.security.input_validation]
enabled = true
max_input_length = 10000

[agent.security.pii_detection]
enabled = true
action = "warn"  # warn, block, or redact
```

## Environment Variables

Override configuration with environment variables:

### Azure Authentication

| Variable | Description |
|----------|-------------|
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | Service principal client ID |
| `AZURE_CLIENT_SECRET` | Service principal secret |

### Azure OpenAI

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Overrides `[[agent.models]]` endpoint |
| `AZURE_OPENAI_DEPLOYMENT` | Overrides deployment name |
| `AZURE_OPENAI_API_VERSION` | Overrides API version |

### Other Providers

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `GOOGLE_API_KEY` | Google API key |

### Redis

| Variable | Description |
|----------|-------------|
| `REDIS_HOST` | Override Redis host |
| `REDIS_PORT` | Override Redis port |
| `REDIS_PASSWORD` | Redis password (if required) |

### Storage

| Variable | Description |
|----------|-------------|
| `ADLS_ACCOUNT_NAME` | Override storage account |
| `ADLS_CONTAINER` | Override container name |

### Observability

| Variable | Description |
|----------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector endpoint |
| `OTEL_SERVICE_NAME` | Service name for traces |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Azure Monitor connection |

### General

| Variable | Description |
|----------|-------------|
| `LOG_LEVEL` | Override log level |

## Variable Substitution

Use environment variables in config values:

```toml
[[agent.mcp]]
name = "d365"
type = "d365"

[agent.mcp.oauth]
client_secret = "${D365_CLIENT_SECRET}"  # Substituted at runtime
```

## Configuration Validation

The framework validates configuration on startup. Invalid configuration will raise errors:

```python
from src.config import load_config

try:
    config = load_config()
except ValueError as e:
    print(f"Configuration error: {e}")
```

### Common Validation Errors

- **Missing required field**: `endpoint` not specified for Azure OpenAI
- **Invalid model name**: `default_model` doesn't match any `[[agent.models]]`
- **Invalid URL**: MCP server URL is malformed
- **Type mismatch**: Boolean value expected, got string

## Configuration Examples

### Minimal (Development)

```toml
[agent]
log_level = "DEBUG"
default_model = "azure_openai"

[[agent.models]]
name = "azure_openai"
provider = "azure_openai"
endpoint = "https://my-resource.openai.azure.com/"
deployment = "gpt-4o"
```

### Full Production

```toml
[agent]
system_prompt = "config/system_prompt.txt"
log_level = "INFO"
default_model = "azure_openai"

[[agent.models]]
name = "azure_openai"
provider = "azure_openai"
endpoint = "https://prod-openai.openai.azure.com/"
deployment = "gpt-4o"
api_version = "2024-10-01-preview"

[agent.tools]
config_dir = "config/tools"
tool_modules = ["src.tools.production"]

[[agent.mcp]]
name = "calculator"
type = "stdio"
enabled = true
command = "uvx"
args = ["mcp-server-calculator"]

[agent.memory.cache]
enabled = true
host = "prod-redis.redis.cache.windows.net"
port = 6380
ssl = true
ttl = 300
prefix = "chat:"

[agent.memory.persistence]
enabled = true
account_name = "prodstorageaccount"
container = "chat-history"
folder = "threads"
schedule = "ttl+60"

[agent.security]
require_authentication = true
allowed_origins = ["https://myapp.example.com"]

[agent.security.rate_limiting]
enabled = true
requests_per_minute = 60

[agent.security.input_validation]
enabled = true
max_input_length = 10000

[agent.security.pii_detection]
enabled = true
action = "warn"
```

## Related Documentation

- [Config Reference](../reference/config-reference.md) — Complete TOML reference
- [Environment Variables](../reference/environment-variables.md) — All env vars
- [Security](../security.md) — Security configuration
- [Memory](../memory.md) — Session management

---
*Last updated: 2026-01-17*
