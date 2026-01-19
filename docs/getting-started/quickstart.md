# Quickstart

Get your AI agent running in under 5 minutes.

## Prerequisites

- Python 3.10 or higher
- Azure OpenAI resource with a deployed model
- Azure CLI logged in (`az login`)

## Step 1: Clone and Install

```bash
# Clone the repository
git clone https://github.com/your-org/MSFT-AGENT-FRAMEWORK.git
cd MSFT-AGENT-FRAMEWORK

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package
pip install -e .
```

## Step 2: Configure

Copy the example configuration:

```bash
cp config/agent.toml.example config/agent.toml
```

Edit `config/agent.toml` with your Azure OpenAI details:

```toml
[agent]
system_prompt = "config/system_prompt.txt"
log_level = "INFO"
default_model = "azure_openai"

[[agent.models]]
name = "azure_openai"
provider = "azure_openai"
endpoint = "https://YOUR-RESOURCE.openai.azure.com/"
deployment = "gpt-4o"
api_version = "2024-10-01-preview"
```

Replace `YOUR-RESOURCE` with your Azure OpenAI resource name.

## Step 3: Set Up Authentication

The framework uses Azure Identity for authentication. The easiest way is to log in with Azure CLI:

```bash
az login
```

Your Azure account needs the **Cognitive Services OpenAI User** role on the Azure OpenAI resource.

## Step 4: Run Your Agent

Create a simple test script:

```python
# test_agent.py
import asyncio
from src.agent import AIAssistant

async def main():
    # Create and initialize the assistant
    async with AIAssistant() as assistant:
        # Ask a question
        result = await assistant.process_question(
            "Hello! What can you help me with today?"
        )
        print(f"Response: {result.response}")
        print(f"Chat ID: {result.chat_id}")

if __name__ == "__main__":
    asyncio.run(main())
```

Run it:

```bash
python test_agent.py
```

You should see a response from your AI agent!

## Step 5: Try More Features

### Streaming Response

```python
async with AIAssistant() as assistant:
    async for chunk in await assistant.process_question_stream(
        "Tell me a short joke"
    ):
        print(chunk.text, end="", flush=True)
    print()  # Newline at the end
```

### Session Continuity

```python
async with AIAssistant() as assistant:
    # First message
    result1 = await assistant.process_question("My name is Alice")
    chat_id = result1.chat_id
    print(f"Response 1: {result1.response}")

    # Follow-up using the same chat_id
    result2 = await assistant.process_question(
        "What's my name?",
        chat_id=chat_id
    )
    print(f"Response 2: {result2.response}")
    # Output: "Your name is Alice"
```

### Health Check

```python
async with AIAssistant() as assistant:
    health = await assistant.health_check()
    print(f"Status: {health.status}")
    for component in health.components:
        print(f"  - {component.name}: {component.status}")
```

## What's Next?

Now that you have a working agent, explore these topics:

### Add Custom Tools

Extend your agent's capabilities:

```python
from src.tools import ai_function, register_tool

@register_tool(tags=["utilities"])
@ai_function
def get_current_time() -> str:
    """Get the current time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

See [Tools Guide](../tools.md) for details.

### Enable Session Persistence

Store chat history in Redis and ADLS:

```toml
[agent.memory.cache]
enabled = true
host = "your-redis.redis.cache.windows.net"
port = 6380
ssl = true

[agent.memory.persistence]
enabled = true
account_name = "yourstorageaccount"
container = "chat-history"
```

See [Memory Guide](../memory.md) for details.

### Connect MCP Servers

Add external tool servers:

```toml
[[agent.mcp]]
name = "calculator"
type = "stdio"
command = "uvx"
args = ["mcp-server-calculator"]
```

See [MCP Integration Guide](../guides/mcp-integration.md) for details.

### Deploy to Production

Choose your deployment option:

- [Docker](../deployment/docker.md) — Simple container deployment
- [Kubernetes](../deployment/kubernetes.md) — Production orchestration
- [Azure](../deployment/azure-deployment.md) — Azure PaaS services

## Troubleshooting

### Authentication Errors

```
DefaultAzureCredential failed to retrieve a token
```

**Solution**: Run `az login` and ensure your account has access to the Azure OpenAI resource.

### Model Not Found

```
The model deployment 'gpt-4o' was not found
```

**Solution**: Verify the deployment name in Azure OpenAI Studio matches your config.

### Connection Timeout

```
Connection timed out
```

**Solution**: Check your network connectivity and firewall rules for Azure services.

For more troubleshooting help, see [Troubleshooting Guide](../troubleshooting.md).

## Related Documentation

- [Installation](installation.md) — Detailed installation guide
- [Configuration](configuration.md) — Complete configuration reference
- [Architecture](../architecture.md) — System overview

---
*Last updated: 2026-01-17*
