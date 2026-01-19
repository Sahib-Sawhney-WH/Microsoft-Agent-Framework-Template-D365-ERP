# Installation

This guide covers detailed installation options for the MSFT Agent Framework.

## Prerequisites

### Required

- **Python 3.10+** — Python 3.10, 3.11, or 3.12
- **pip** — Python package manager
- **Azure OpenAI** — Deployed Azure OpenAI resource with a model

### Optional

- **Azure Cache for Redis** — For session caching (recommended for production)
- **Azure Blob Storage** — For persistent chat history
- **Azure Key Vault** — For secrets management

## Installation Methods

### Method 1: From Source (Recommended)

Clone and install in development mode:

```bash
# Clone repository
git clone https://github.com/your-org/MSFT-AGENT-FRAMEWORK.git
cd MSFT-AGENT-FRAMEWORK

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install in editable mode
pip install -e .
```

### Method 2: With Optional Dependencies

Install with additional features:

```bash
# Development tools (pytest, black, ruff, mypy)
pip install -e ".[dev]"

# Observability (Azure Monitor, Jaeger exporters)
pip install -e ".[observability]"

# Multi-model support (Anthropic, Google)
pip install -e ".[multi-model]"

# Everything
pip install -e ".[all]"
```

### Method 3: Production Install

For production deployments without editable mode:

```bash
pip install .
```

## Verifying Installation

### Check Package Installation

```bash
pip show msft-agent-framework
```

Expected output:

```
Name: msft-agent-framework
Version: 1.0.0
Summary: Extensible AI Assistant using Microsoft Agent Framework
```

### Check Dependencies

```bash
pip check
```

Should return no errors.

### Test Import

```python
python -c "from src.agent import AIAssistant; print('Import successful!')"
```

## Dependencies

### Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `azure-identity` | >=1.15.0 | Azure authentication |
| `openai` | >=1.0.0 | OpenAI/Azure OpenAI client |
| `agent-framework` | >=0.1.0 | Microsoft Agent Framework |
| `structlog` | >=23.1.0 | Structured logging |
| `pydantic` | >=2.0.0 | Data validation |
| `redis` | >=5.0.0 | Redis client |
| `azure-storage-blob` | >=12.14.0 | Azure Blob Storage client |

### Optional Dependencies

#### Development (`dev`)

```
pytest>=7.0.0
pytest-asyncio>=0.21.0
black>=23.0.0
ruff>=0.1.0
mypy>=1.0.0
```

#### Observability (`observability`)

```
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp>=1.20.0
azure-monitor-opentelemetry-exporter>=1.0.0b21
```

#### Multi-Model (`multi-model`)

```
anthropic>=0.25.0
google-generativeai>=0.5.0
```

## Azure Authentication Setup

The framework uses Azure Identity (`DefaultAzureCredential`) which tries multiple authentication methods:

### Option 1: Azure CLI (Development)

```bash
az login
```

### Option 2: Environment Variables (CI/CD)

```bash
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"
```

### Option 3: Managed Identity (Production)

No configuration needed — works automatically on Azure services.

### Required Permissions

Your identity needs these RBAC roles:

| Resource | Role |
|----------|------|
| Azure OpenAI | Cognitive Services OpenAI User |
| Azure Cache for Redis | Redis Cache Contributor |
| Azure Blob Storage | Storage Blob Data Contributor |
| Azure Key Vault | Key Vault Secrets User |

Grant access:

```bash
# Azure OpenAI
az role assignment create \
  --role "Cognitive Services OpenAI User" \
  --assignee your-principal-id \
  --scope /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}

# Redis
az role assignment create \
  --role "Redis Cache Contributor" \
  --assignee your-principal-id \
  --scope /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Cache/redis/{cache}

# Storage
az role assignment create \
  --role "Storage Blob Data Contributor" \
  --assignee your-principal-id \
  --scope /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Storage/storageAccounts/{account}
```

## IDE Setup

### VS Code

Recommended extensions:

- **Python** (ms-python.python)
- **Pylance** (ms-python.vscode-pylance)
- **Black Formatter** (ms-python.black-formatter)
- **Ruff** (charliermarsh.ruff)

Settings (`.vscode/settings.json`):

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.analysis.typeCheckingMode": "basic",
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter",
    "editor.formatOnSave": true
  },
  "ruff.enable": true
}
```

### PyCharm

1. Open project folder
2. Configure interpreter: `File > Settings > Project > Python Interpreter`
3. Select `.venv` interpreter
4. Enable Black formatter: `Settings > Tools > Black`

## Project Structure

After installation, your project structure should look like:

```
MSFT-AGENT-FRAMEWORK/
├── .venv/                 # Virtual environment
├── config/
│   ├── agent.toml         # Your configuration (copy from example)
│   ├── agent.toml.example # Example configuration
│   ├── system_prompt.txt  # Agent system prompt
│   └── tools/             # JSON tool definitions
├── src/
│   ├── agent/             # Core agent module
│   ├── config/            # Configuration loader
│   ├── loaders/           # Tool and MCP loaders
│   ├── memory/            # Session management
│   ├── models/            # Multi-model registry
│   ├── observability/     # Tracing and metrics
│   ├── security/          # Security features
│   ├── tools/             # Tool utilities
│   └── health.py          # Health checks
├── docs/                  # Documentation
├── tests/                 # Test suite
├── deployment/            # Docker and K8s files
├── pyproject.toml         # Project configuration
└── README.md
```

## Troubleshooting Installation

### pip Install Fails

```
ERROR: Could not find a version that satisfies the requirement agent-framework>=0.1.0
```

**Solution**: Ensure you have access to the package source or configure the correct pip index.

### Permission Denied

```
ERROR: Could not install packages due to an EnvironmentError: [Errno 13] Permission denied
```

**Solution**: Use a virtual environment instead of system Python:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### SSL Certificate Errors

```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed
```

**Solution**: Update certificates:

```bash
# macOS
pip install --upgrade certifi
# or
/Applications/Python\ 3.x/Install\ Certificates.command
```

### Import Errors

```
ModuleNotFoundError: No module named 'src'
```

**Solution**: Ensure you installed in editable mode:

```bash
pip install -e .
```

## Uninstalling

```bash
# Uninstall package
pip uninstall msft-agent-framework

# Remove virtual environment
rm -rf .venv
```

## Next Steps

- [Configuration](configuration.md) — Configure your agent
- [Quickstart](quickstart.md) — Run your first agent
- [Architecture](../architecture.md) — Understand the system

---
*Last updated: 2026-01-17*
