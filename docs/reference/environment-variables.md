# Environment Variables Reference

Complete reference for all environment variables used by the MSFT Agent Framework.

## Overview

Environment variables can override configuration file settings and provide sensitive values like credentials. Variables are loaded at startup.

---

## Azure Authentication

These variables configure Azure Identity authentication. At least one authentication method is required.

### DefaultAzureCredential (Recommended)

The framework uses `DefaultAzureCredential` which tries multiple methods in order:

1. Environment variables (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`)
2. Managed Identity
3. Azure CLI (`az login`)
4. Visual Studio Code
5. Azure PowerShell

### Service Principal

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_TENANT_ID` | Yes* | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | Yes* | Application (client) ID |
| `AZURE_CLIENT_SECRET` | Yes* | Client secret value |

*Required when using service principal authentication.

**Example:**

```bash
export AZURE_TENANT_ID="12345678-1234-1234-1234-123456789012"
export AZURE_CLIENT_ID="87654321-4321-4321-4321-210987654321"
export AZURE_CLIENT_SECRET="your-secret-value"
```

### Managed Identity

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_CLIENT_ID` | No | Client ID for user-assigned managed identity |

For **system-assigned** managed identity, no variables needed.

For **user-assigned** managed identity:

```bash
export AZURE_CLIENT_ID="managed-identity-client-id"
```

---

## Azure OpenAI

Override Azure OpenAI configuration from `agent.toml`.

| Variable | Required | Description | Overrides |
|----------|----------|-------------|-----------|
| `AZURE_OPENAI_ENDPOINT` | No | Azure OpenAI endpoint URL | `[[agent.models]].endpoint` |
| `AZURE_OPENAI_DEPLOYMENT` | No | Model deployment name | `[[agent.models]].deployment` |
| `AZURE_OPENAI_API_VERSION` | No | API version | `[[agent.models]].api_version` |
| `AZURE_OPENAI_API_KEY` | No | API key (alternative to AAD auth) | N/A |

**Example:**

```bash
export AZURE_OPENAI_ENDPOINT="https://my-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"
export AZURE_OPENAI_API_VERSION="2024-10-01-preview"
```

---

## Other Model Providers

API keys for non-Azure providers.

| Variable | Provider | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | OpenAI | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic | Anthropic API key for Claude |
| `GOOGLE_API_KEY` | Google | Google API key for Gemini |

**Example:**

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="AIza..."
```

---

## Redis Configuration

Override Redis cache settings from `agent.toml`.

| Variable | Required | Description | Overrides |
|----------|----------|-------------|-----------|
| `REDIS_HOST` | No | Redis hostname | `[agent.memory.cache].host` |
| `REDIS_PORT` | No | Redis port | `[agent.memory.cache].port` |
| `REDIS_PASSWORD` | No | Redis password (if required) | N/A |
| `REDIS_SSL` | No | Use SSL (`true`/`false`) | `[agent.memory.cache].ssl` |
| `REDIS_DATABASE` | No | Database number | `[agent.memory.cache].database` |

**Example:**

```bash
export REDIS_HOST="my-redis.redis.cache.windows.net"
export REDIS_PORT="6380"
export REDIS_SSL="true"
```

---

## Azure Blob Storage

Override ADLS persistence settings from `agent.toml`.

| Variable | Required | Description | Overrides |
|----------|----------|-------------|-----------|
| `ADLS_ACCOUNT_NAME` | No | Storage account name | `[agent.memory.persistence].account_name` |
| `ADLS_CONTAINER` | No | Container name | `[agent.memory.persistence].container` |
| `ADLS_CONNECTION_STRING` | No | Connection string (alternative auth) | N/A |

**Example:**

```bash
export ADLS_ACCOUNT_NAME="mystorageaccount"
export ADLS_CONTAINER="chat-history"
```

---

## D365 Integration

Variables for Dynamics 365 MCP integration.

| Variable | Required | Description |
|----------|----------|-------------|
| `D365_CLIENT_SECRET` | Yes* | D365 OAuth client secret |
| `D365_ENVIRONMENT_URL` | No | D365 environment URL |

*Required when using D365 MCP with client credentials.

**Example:**

```bash
export D365_CLIENT_SECRET="your-d365-secret"
export D365_ENVIRONMENT_URL="https://myorg.operations.dynamics.com"
```

---

## Observability

Configure OpenTelemetry and monitoring.

| Variable | Required | Description |
|----------|----------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | OpenTelemetry collector endpoint |
| `OTEL_SERVICE_NAME` | No | Service name for traces |
| `OTEL_RESOURCE_ATTRIBUTES` | No | Additional resource attributes |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | No | Azure Application Insights connection |

**Example:**

```bash
# OpenTelemetry Collector
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317"
export OTEL_SERVICE_NAME="msft-agent-framework"

# Azure Application Insights
export APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=..."
```

### Trace Sampling

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_TRACES_SAMPLER` | `parentbased_always_on` | Sampling strategy |
| `OTEL_TRACES_SAMPLER_ARG` | `1.0` | Sampling ratio (0.0-1.0) |

**Example (sample 10% of traces):**

```bash
export OTEL_TRACES_SAMPLER="parentbased_traceidratio"
export OTEL_TRACES_SAMPLER_ARG="0.1"
```

---

## Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `json` | Log format: `json`, `console` |

**Example:**

```bash
export LOG_LEVEL="DEBUG"
export LOG_FORMAT="console"  # Human-readable for development
```

---

## General Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_PATH` | `config/agent.toml` | Path to configuration file |
| `PYTHONUNBUFFERED` | `1` | Disable output buffering (recommended for containers) |
| `PYTHONDONTWRITEBYTECODE` | `1` | Don't write `.pyc` files |

**Example:**

```bash
export CONFIG_PATH="/etc/msft-agent/agent.toml"
export PYTHONUNBUFFERED="1"
```

---

## Variable Precedence

When the same setting is configured in multiple places, the order of precedence is:

1. **Environment variables** (highest priority)
2. **Configuration file** (`agent.toml`)
3. **Built-in defaults** (lowest priority)

**Example:**

```toml
# agent.toml
[agent.memory.cache]
host = "config-redis.redis.cache.windows.net"
```

```bash
# Environment variable - takes precedence
export REDIS_HOST="env-redis.redis.cache.windows.net"
```

Result: Redis connects to `env-redis.redis.cache.windows.net`

---

## Environment File (.env)

For local development, use a `.env` file:

```bash
# .env
AZURE_TENANT_ID=12345678-1234-1234-1234-123456789012
AZURE_CLIENT_ID=87654321-4321-4321-4321-210987654321
AZURE_CLIENT_SECRET=your-secret

AZURE_OPENAI_ENDPOINT=https://my-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_SSL=false

LOG_LEVEL=DEBUG
```

Load with:

```bash
# Bash
set -a; source .env; set +a

# Or use python-dotenv
pip install python-dotenv
```

**Important:** Never commit `.env` files to version control. Add to `.gitignore`:

```gitignore
.env
.env.*
!.env.example
```

---

## Docker Environment

Pass variables to Docker containers:

```bash
# Individual variables
docker run -e AZURE_OPENAI_ENDPOINT=... -e LOG_LEVEL=INFO myimage

# From file
docker run --env-file .env myimage
```

Docker Compose:

```yaml
services:
  agent:
    image: msft-agent-framework
    environment:
      - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
      - LOG_LEVEL=INFO
    env_file:
      - .env
```

---

## Kubernetes Secrets

Reference secrets in Kubernetes:

```yaml
env:
  - name: AZURE_CLIENT_SECRET
    valueFrom:
      secretKeyRef:
        name: azure-credentials
        key: client-secret
  - name: AZURE_OPENAI_ENDPOINT
    valueFrom:
      configMapKeyRef:
        name: agent-config
        key: openai-endpoint
```

---

## Security Best Practices

1. **Never log secrets** — Ensure sensitive variables aren't logged
2. **Use Key Vault** — Store secrets in Azure Key Vault for production
3. **Rotate credentials** — Regularly rotate client secrets and API keys
4. **Limit exposure** — Use managed identity where possible
5. **Audit access** — Monitor who accesses secrets

---

## Complete Example

Development environment:

```bash
# Authentication
export AZURE_TENANT_ID="..."
export AZURE_CLIENT_ID="..."
export AZURE_CLIENT_SECRET="..."

# Azure OpenAI
export AZURE_OPENAI_ENDPOINT="https://dev-openai.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"

# Local Redis
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
export REDIS_SSL="false"

# Development settings
export LOG_LEVEL="DEBUG"
export LOG_FORMAT="console"
```

Production environment:

```bash
# Managed Identity - no auth variables needed

# Azure OpenAI (from Key Vault reference)
export AZURE_OPENAI_ENDPOINT="https://prod-openai.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"

# Azure Redis
export REDIS_HOST="prod-redis.redis.cache.windows.net"
export REDIS_PORT="6380"
export REDIS_SSL="true"

# Production settings
export LOG_LEVEL="INFO"
export LOG_FORMAT="json"

# Observability
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317"
export OTEL_SERVICE_NAME="msft-agent-prod"
export APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=..."
```

---

## Related Documentation

- [Configuration Guide](../getting-started/configuration.md) — Configuration overview
- [Config Reference](config-reference.md) — TOML configuration reference
- [Deployment Overview](../deployment/overview.md) — Deployment options

---
*Last updated: 2026-01-17*
