# Troubleshooting Guide

This guide covers common issues and their solutions when working with the MSFT Agent Framework.

## Quick Diagnostics

### Health Check

First, run a health check to identify issues:

```python
import asyncio
from src.agent import AIAssistant

async def diagnose():
    async with AIAssistant() as assistant:
        health = await assistant.health_check()
        print(f"Overall: {health.status}")
        for c in health.components:
            status = "OK" if c.status == "healthy" else "ISSUE"
            print(f"  [{status}] {c.name}: {c.message or c.status}")

asyncio.run(diagnose())
```

### Enable Debug Logging

```bash
export LOG_LEVEL=DEBUG
python your_script.py
```

Or in code:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Authentication Errors

### "DefaultAzureCredential failed to retrieve a token"

**Symptoms:**
```
azure.identity.CredentialUnavailableError: DefaultAzureCredential failed to retrieve a token from the included credentials.
```

**Solutions:**

1. **Azure CLI login:**
   ```bash
   az login
   az account show  # Verify logged in
   ```

2. **Environment variables (for service principal):**
   ```bash
   export AZURE_TENANT_ID="your-tenant-id"
   export AZURE_CLIENT_ID="your-client-id"
   export AZURE_CLIENT_SECRET="your-secret"
   ```

3. **Check RBAC permissions:**
   ```bash
   # Verify role assignment
   az role assignment list --assignee your-principal-id
   ```

### "401 Unauthorized" from Azure OpenAI

**Symptoms:**
```
openai.AuthenticationError: Error code: 401
```

**Solutions:**

1. Verify endpoint URL format:
   ```
   https://YOUR-RESOURCE.openai.azure.com/
   ```
   (Note the trailing slash)

2. Check deployment name matches exactly

3. Verify identity has "Cognitive Services OpenAI User" role:
   ```bash
   az role assignment create \
     --role "Cognitive Services OpenAI User" \
     --assignee your-principal-id \
     --scope /subscriptions/.../Microsoft.CognitiveServices/accounts/your-resource
   ```

---

## Azure OpenAI Errors

### "The model deployment was not found"

**Symptoms:**
```
openai.NotFoundError: The model deployment 'gpt-4o' was not found
```

**Solutions:**

1. Verify deployment exists in Azure OpenAI Studio
2. Check deployment name is exact (case-sensitive)
3. Confirm endpoint matches the resource with the deployment

### "Rate limit exceeded"

**Symptoms:**
```
openai.RateLimitError: Rate limit reached
```

**Solutions:**

1. Check quota in Azure OpenAI Studio
2. Implement retry with exponential backoff (built-in)
3. Request quota increase from Azure

### "Context length exceeded"

**Symptoms:**
```
openai.BadRequestError: This model's maximum context length is 8192 tokens
```

**Solutions:**

1. Enable memory summarization:
   ```toml
   [agent.memory.summarization]
   enabled = true
   max_tokens = 4000
   target_tokens = 2000
   ```

2. Use a model with larger context (gpt-4-turbo: 128K tokens)

---

## Redis Errors

### "Connection refused"

**Symptoms:**
```
redis.exceptions.ConnectionError: Connection refused
```

**Solutions:**

1. **Local Redis:** Verify Redis is running:
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

2. **Azure Redis:** Check firewall rules allow your IP

3. **SSL issues:** Ensure `ssl = true` for Azure Redis:
   ```toml
   [agent.memory.cache]
   ssl = true
   port = 6380
   ```

### "Authentication required"

**Symptoms:**
```
redis.exceptions.AuthenticationError: AUTH failed
```

**Solutions:**

1. For Azure Redis with AAD auth, ensure managed identity has access

2. For password auth:
   ```bash
   export REDIS_PASSWORD="your-password"
   ```

### "Redis not connected, using fallback"

This is a warning, not an error. The framework will work without Redis but won't cache sessions.

**To enable Redis:**

1. Verify configuration is correct
2. Check network connectivity
3. Review Redis logs

---

## Azure Blob Storage Errors

### "ContainerNotFound"

**Symptoms:**
```
azure.core.exceptions.ResourceNotFoundError: ContainerNotFound
```

**Solutions:**

1. Create the container:
   ```bash
   az storage container create --name chat-history --account-name youraccount
   ```

2. Verify container name in config matches exactly

### "AuthorizationPermissionMismatch"

**Symptoms:**
```
azure.core.exceptions.HttpResponseError: AuthorizationPermissionMismatch
```

**Solutions:**

Grant "Storage Blob Data Contributor" role:
```bash
az role assignment create \
  --role "Storage Blob Data Contributor" \
  --assignee your-principal-id \
  --scope /subscriptions/.../storageAccounts/youraccount
```

---

## MCP Errors

### "Failed to start stdio server"

**Symptoms:**
```
MCPConnectionError: Failed to start stdio server 'calculator'
```

**Solutions:**

1. Verify command exists:
   ```bash
   which uvx  # or: where uvx on Windows
   ```

2. Test manually:
   ```bash
   uvx mcp-server-calculator
   ```

3. Check for Python path issues:
   ```toml
   [[agent.mcp]]
   name = "custom"
   type = "stdio"
   command = "python"
   args = ["-m", "mymodule"]
   env = { PYTHONPATH = "/app/src" }
   ```

### "Connection refused" (HTTP MCP)

**Solutions:**

1. Verify URL is correct
2. Check server is running
3. Check firewall/network rules
4. Verify TLS/SSL settings

### "401 Unauthorized" (MCP with OAuth)

**Solutions:**

1. Check OAuth credentials
2. Verify token endpoint URL
3. Check scopes are correct
4. Regenerate client secret if expired

---

## Configuration Errors

### "Configuration file not found"

**Symptoms:**
```
FileNotFoundError: config/agent.toml not found
```

**Solutions:**

1. Copy example config:
   ```bash
   cp config/agent.toml.example config/agent.toml
   ```

2. Specify custom path:
   ```python
   assistant = AIAssistant(config_path="/path/to/agent.toml")
   ```

### "Invalid configuration"

**Symptoms:**
```
ValueError: Model 'xyz' not found in configuration
```

**Solutions:**

1. Verify model name matches `[[agent.models]].name`
2. Check TOML syntax (use a TOML validator)
3. Ensure required fields are present

---

## Import Errors

### "ModuleNotFoundError: No module named 'src'"

**Solutions:**

1. Install in editable mode:
   ```bash
   pip install -e .
   ```

2. Or add to PYTHONPATH:
   ```bash
   export PYTHONPATH="${PYTHONPATH}:/path/to/project"
   ```

### "ImportError: cannot import name 'AIAssistant'"

**Solutions:**

1. Verify package is installed:
   ```bash
   pip show msft-agent-framework
   ```

2. Check Python version:
   ```bash
   python --version  # Must be 3.10+
   ```

---

## Performance Issues

### Slow Response Times

**Diagnostics:**

```python
import time

start = time.time()
result = await assistant.process_question("Hello")
print(f"Time: {time.time() - start:.2f}s")
```

**Solutions:**

1. Check health of components:
   ```python
   health = await assistant.health_check()
   for c in health.components:
       print(f"{c.name}: {c.latency_ms}ms")
   ```

2. Use a faster model (gpt-4o-mini vs gpt-4)

3. Enable caching:
   ```toml
   [agent.memory.cache]
   enabled = true
   ```

### High Memory Usage

**Solutions:**

1. Enable memory summarization
2. Reduce cache TTL
3. Limit context size
4. Check for memory leaks with `tracemalloc`

---

## Tool Errors

### "Tool not found"

**Symptoms:**
```
ToolNotFoundError: Tool 'my_tool' not found
```

**Solutions:**

1. Verify tool is registered:
   ```python
   tools = assistant.get_tools()
   print([t.name for t in tools])
   ```

2. Check tool module is in config:
   ```toml
   [agent.tools]
   tool_modules = ["src.my_tools"]
   ```

3. Verify `@register_tool` decorator is applied

### "Tool execution failed"

**Solutions:**

1. Enable debug logging to see full error
2. Test tool independently:
   ```python
   result = my_tool(test_input)
   ```

3. Check tool has proper error handling

---

## Docker/Container Issues

### Container Won't Start

```bash
# Check logs
docker logs msft-agent

# Check exit code
docker inspect msft-agent --format='{{.State.ExitCode}}'
```

### Health Check Failing

```bash
# Test health endpoint
docker exec msft-agent curl http://localhost:8000/health

# Check container health
docker inspect --format='{{.State.Health.Status}}' msft-agent
```

---

## Getting More Help

### Collect Diagnostic Information

```python
import sys
import platform

print(f"Python: {sys.version}")
print(f"Platform: {platform.platform()}")

# Package versions
import pkg_resources
for pkg in ['openai', 'azure-identity', 'redis', 'structlog']:
    try:
        print(f"{pkg}: {pkg_resources.get_distribution(pkg).version}")
    except:
        print(f"{pkg}: not installed")
```

### Debug Mode Script

```python
import asyncio
import logging

# Enable all logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def debug_run():
    from src.agent import AIAssistant

    try:
        async with AIAssistant() as assistant:
            # Health check
            health = await assistant.health_check()
            print(f"\n=== Health Check ===")
            print(f"Status: {health.status}")
            for c in health.components:
                print(f"  {c.name}: {c.status} - {c.message}")

            # Test query
            print(f"\n=== Test Query ===")
            result = await assistant.process_question("Hello, test message")
            print(f"Response: {result.response[:100]}...")

    except Exception as e:
        print(f"\n=== Error ===")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(debug_run())
```

### Report an Issue

When reporting issues, include:

1. Python version and platform
2. Package versions
3. Configuration (redact secrets)
4. Full error traceback
5. Steps to reproduce

---

## Related Documentation

- [Installation](getting-started/installation.md) — Setup guide
- [Configuration](getting-started/configuration.md) — Config reference
- [Architecture](architecture.md) — System design
- [Health Checks](deployment/overview.md#health-endpoints) — Health monitoring

---
*Last updated: 2026-01-17*
