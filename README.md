# MSFT Agent Framework

A production-ready AI agent template using the [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview) with dynamic tool loading, MCP support, multi-model providers, and enterprise features.

## Features

- **Dynamic Tool Loading** — Hybrid decorator + JSON tool discovery
- **Multi-Model Support** — Azure OpenAI, OpenAI, and custom providers via registry
- **MCP Integration** — Connect to external MCP servers (stdio, HTTP, WebSocket)
- **Multi-Agent Workflows** — Sequential and graph-based agent pipelines
- **Session Management** — Redis cache + ADLS persistence with auto-summarization
- **Observability** — OpenTelemetry tracing and metrics
- **Security** — Rate limiting, input validation, prompt injection detection
- **Health Checks** — Kubernetes-ready readiness/liveness probes

## Quick Start

### Install

```bash
git clone https://github.com/Sahib-Sawhney-WH/Microsoft-Agent-Framework-Template-D365-ERP.git
cd MSFT-AGENT-FRAMEWORK
pip install -e .
```

### Configure

Edit `config/agent.toml`:

```toml
[agent.azure_openai]
endpoint = "https://your-resource.openai.azure.com/"
deployment = "gpt-4o"
```

Or set environment variables:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"
```

### Run

```python
import asyncio
from src.agent import AIAssistant

async def main():
    async with AIAssistant() as assistant:
        result = await assistant.process_question("Hello! What can you help me with?")
        print(result.response)

asyncio.run(main())
```

## Project Structure

```
MSFT-AGENT-FRAMEWORK/
├── config/
│   ├── agent.toml              # Main configuration
│   ├── system_prompt.txt       # Agent system prompt
│   └── tools/                  # JSON tool definitions (optional)
├── src/
│   ├── agent/                  # Core agent (AIAssistant, middleware)
│   ├── config/                 # TOML configuration loader
│   ├── loaders/                # Tool, MCP, and workflow loaders
│   ├── memory/                 # Session management (Redis, ADLS)
│   ├── models/                 # Multi-model provider registry
│   ├── observability/          # Tracing and metrics
│   ├── security/               # Rate limiting, input validation
│   ├── tools/                  # Tool exports (@ai_function, etc.)
│   └── health.py               # Health check system
├── docs/
│   ├── architecture.md         # System architecture diagrams
│   ├── observability.md        # Tracing and metrics guide
│   ├── security.md             # Security features guide
│   ├── memory.md               # Session management guide
│   └── azure-setup.md          # Azure resource setup
└── tests/
```

## Adding Tools

Use the decorator pattern (recommended):

```python
from src.tools import ai_function, register_tool, Annotated, Field

@register_tool(tags=["utilities"])
@ai_function
def weather_lookup(
    location: Annotated[str, Field(description="City name or coordinates")],
    units: Annotated[str, Field(description="Temperature units")] = "fahrenheit",
) -> str:
    """Get current weather for a location."""
    # Your implementation here
    return f"Weather in {location}: Sunny, 72°F"
```

Tools are auto-discovered from any module listed in `config/agent.toml`:

```toml
[agent.tools]
tool_modules = ["src.example_tool.tools", "src.my_tools"]
```

For JSON-based tools and service pattern, see [docs/architecture.md](docs/architecture.md#tool-loading-architecture).

## Configuration

### Multi-Model Providers

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
endpoint = "https://your-resource.openai.azure.com/"
```

### MCP Servers

```toml
[[agent.mcp]]
name = "calculator"
type = "stdio"
command = "uvx"
args = ["mcp-server-calculator"]
```

### Workflows

```toml
[[agent.workflows]]
name = "content-pipeline"
type = "sequential"

[[agent.workflows.agents]]
name = "Researcher"
instructions = "Research the topic and provide key facts."

[[agent.workflows.agents]]
name = "Writer"
instructions = "Write engaging content based on the research."
```

## Usage Examples

### Streaming Response

```python
async with AIAssistant() as assistant:
    async for chunk in await assistant.process_question_stream("Tell me a joke"):
        print(chunk.text, end="", flush=True)
```

### Run Workflow

```python
async with AIAssistant() as assistant:
    result = await assistant.run_workflow("content-pipeline", "Write about AI trends")
    print(result.response)
```

### Session Continuity

```python
async with AIAssistant() as assistant:
    result1 = await assistant.process_question("My name is Alice")
    chat_id = result1.chat_id

    result2 = await assistant.process_question("What's my name?", chat_id=chat_id)
    # Response: "Your name is Alice"
```

### Health Check

```python
async with AIAssistant() as assistant:
    health = await assistant.health_check()
    print(f"Status: {health.status}")  # healthy, degraded, or unhealthy
```

## Documentation

### Getting Started

| Document | Description |
|----------|-------------|
| [Documentation Hub](docs/index.md) | Start here - navigation and overview |
| [Quickstart](docs/getting-started/quickstart.md) | 5-minute getting started guide |
| [Installation](docs/getting-started/installation.md) | Detailed installation instructions |
| [Configuration](docs/getting-started/configuration.md) | Complete configuration guide |

### Guides

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System diagrams, component overview, request flow |
| [Tools](docs/tools.md) | Creating and loading tools |
| [Memory](docs/memory.md) | Session management, Redis cache, ADLS persistence |
| [Security](docs/security.md) | Rate limiting, input validation, PII detection |
| [Observability](docs/observability.md) | OpenTelemetry tracing and metrics setup |
| [MCP Integration](docs/guides/mcp-integration.md) | Connect to MCP servers |
| [Workflows](docs/guides/workflows.md) | Multi-agent pipelines |

### Deployment

| Document | Description |
|----------|-------------|
| [Deployment Overview](docs/deployment/overview.md) | Compare deployment options |
| [Docker](docs/deployment/docker.md) | Container deployment |
| [Kubernetes](docs/deployment/kubernetes.md) | Production K8s deployment |
| [Azure Deployment](docs/deployment/azure-deployment.md) | Azure PaaS options |
| [Production Checklist](docs/deployment/production-checklist.md) | Pre-deployment verification |

### Reference

| Document | Description |
|----------|-------------|
| [Config Reference](docs/reference/config-reference.md) | Complete TOML reference |
| [API Reference](docs/reference/api.md) | AIAssistant API |
| [Environment Variables](docs/reference/environment-variables.md) | All env vars |

### Integrations & Development

| Document | Description |
|----------|-------------|
| [Azure Setup](docs/azure-setup.md) | Azure resource configuration |
| [D365 MCP Setup](docs/integrations/d365-mcp-setup.md) | Dynamics 365 integration |
| [Contributing](docs/development/contributing.md) | Development setup and guidelines |
| [Testing](docs/development/testing.md) | Running and writing tests |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Deployment

Quickstart with Docker:

```bash
cd deployment
docker build -t msft-agent-framework:latest -f Dockerfile ..
docker run -d \
  -p 8000:8000 \
  -e AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" \
  -e AZURE_OPENAI_DEPLOYMENT="gpt-4o" \
  msft-agent-framework:latest
```

For production deployments, see:
- [Deployment Overview](docs/deployment/overview.md) — Compare options
- [Docker Guide](docs/deployment/docker.md) — Docker and Docker Compose
- [Kubernetes Guide](docs/deployment/kubernetes.md) — K8s manifests and AKS
- [Azure Deployment](docs/deployment/azure-deployment.md) — Container Apps, App Service
- [Production Checklist](docs/deployment/production-checklist.md) — Pre-deployment verification

## Requirements

- Python 3.10+
- Azure OpenAI resource with deployed model
- Azure identity configured (DefaultAzureCredential)

## License

MIT
