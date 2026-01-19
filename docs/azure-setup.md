# Azure Setup Guide

Detailed instructions for configuring Azure resources for the AI Assistant.

## Prerequisites

- Azure CLI installed and logged in (`az login`)
- Appropriate Azure subscription permissions
- Python 3.10+ with `azure-identity` package

## Azure Cache for Redis (AAD Authentication)

Azure Cache for Redis requires **Data Access Policy** configuration for AAD authentication.
Standard RBAC roles (`Redis Cache Contributor`) are NOT sufficient for data operations.

### Step 1: Create Redis Cache

```bash
# Set variables
RESOURCE_GROUP="your-rg"
REDIS_NAME="your-redis"
LOCATION="eastus"

# Create Redis Cache (Premium tier required for AAD auth)
az redis create \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Premium \
  --vm-size P1 \
  --enable-non-ssl-port false \
  --minimum-tls-version 1.2
```

### Step 2: Enable AAD Authentication

```bash
# Enable AAD authentication
az redis update \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --set redisConfiguration.aad-enabled=true
```

### Step 3: Get Your Object ID (OID)

```bash
# Get your signed-in user's Object ID
az ad signed-in-user show --query id -o tsv
```

Save this OID for the next step.

### Step 4: Create Data Access Policy Assignment

```bash
# Get your OID from the previous step
YOUR_OID="<your-object-id>"
YOUR_EMAIL="your.email@company.com"

# Create Data Access Policy assignment with "Data Owner" permissions
az redis access-policy-assignment create \
  --name "your-user-policy" \
  --policy-name "Data Owner" \
  --object-id "$YOUR_OID" \
  --object-id-alias "$YOUR_EMAIL" \
  --redis-cache-name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP
```

**Available Policies:**
- `Data Owner` — Full read/write access (recommended for development)
- `Data Contributor` — Read/write access, no admin commands
- `Data Reader` — Read-only access

### Step 5: Get Connection Information

```bash
# Get hostname
az redis show \
  --name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --query hostName -o tsv

# Output: your-redis.redis.cache.windows.net
```

### Step 6: Configure the Framework

```toml
# config/agent.toml
[agent.memory.cache]
enabled = true
host = "your-redis.redis.cache.windows.net"
port = 6380
ssl = true
ttl = 3600
prefix = "chat:"
```

### Verify Connection

```python
import asyncio
from azure.identity import DefaultAzureCredential
import redis.asyncio as aioredis

async def test_redis():
    credential = DefaultAzureCredential()
    token = credential.get_token("https://redis.azure.com/.default")

    # Extract OID from token for username
    import jwt
    decoded = jwt.decode(token.token, options={"verify_signature": False})
    oid = decoded.get("oid")

    client = aioredis.Redis(
        host="your-redis.redis.cache.windows.net",
        port=6380,
        ssl=True,
        username=oid,
        password=token.token,
    )

    await client.ping()
    print("Redis connection successful!")
    await client.close()

asyncio.run(test_redis())
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `NOAUTH Authentication required` | Data Access Policy not configured |
| `WRONGPASS invalid username-password` | OID doesn't match policy assignment |
| `Connection refused` | Check SSL settings, port 6380 |
| `ERR unknown command` | Policy doesn't include required permissions |

## Azure Blob Storage (ADLS Gen2)

The persistence layer uses the Azure Blob Storage API. Hierarchical Namespace (HNS)
is NOT required, so any storage account works.

### Step 1: Create Storage Account

```bash
# Set variables
STORAGE_ACCOUNT="yourstorageaccount"
RESOURCE_GROUP="your-rg"
LOCATION="eastus"

# Create storage account
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2
```

### Step 2: Create Container

```bash
# Create container for chat history
az storage container create \
  --name chat-history \
  --account-name $STORAGE_ACCOUNT \
  --auth-mode login
```

### Step 3: Assign RBAC Role

```bash
# Get your OID
YOUR_OID=$(az ad signed-in-user show --query id -o tsv)

# Get storage account resource ID
STORAGE_ID=$(az storage account show \
  --name $STORAGE_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --query id -o tsv)

# Assign Storage Blob Data Contributor role
az role assignment create \
  --assignee "$YOUR_OID" \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_ID"
```

**Available Roles:**
- `Storage Blob Data Contributor` — Read/write/delete blobs (recommended)
- `Storage Blob Data Reader` — Read-only access
- `Storage Blob Data Owner` — Full access including permissions

### Step 4: Configure the Framework

```toml
# config/agent.toml
[agent.memory.persistence]
enabled = true
account_name = "yourstorageaccount"
container = "chat-history"
folder = "threads"
schedule = "ttl+300"
```

### Verify Connection

```python
import asyncio
from azure.identity import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

async def test_storage():
    credential = DefaultAzureCredential()

    service = BlobServiceClient(
        account_url="https://yourstorageaccount.blob.core.windows.net",
        credential=credential
    )

    container = service.get_container_client("chat-history")
    async for blob in container.list_blobs():
        print(f"Found blob: {blob.name}")

    print("Storage connection successful!")
    await service.close()

asyncio.run(test_storage())
```

### Common Issues

| Issue | Solution |
|-------|----------|
| `AuthorizationPermissionMismatch` | RBAC role not assigned or not propagated |
| `ContainerNotFound` | Container doesn't exist |
| `AccountNotFound` | Storage account name incorrect |
| `InvalidAuthenticationInfo` | DefaultAzureCredential has no valid token |

## Azure OpenAI

### Step 1: Create Azure OpenAI Resource

```bash
# Set variables
AOAI_NAME="your-openai"
RESOURCE_GROUP="your-rg"
LOCATION="eastus"

# Create Azure OpenAI resource
az cognitiveservices account create \
  --name $AOAI_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --kind OpenAI \
  --sku S0
```

### Step 2: Deploy a Model

```bash
# Deploy gpt-4o model
az cognitiveservices account deployment create \
  --name $AOAI_NAME \
  --resource-group $RESOURCE_GROUP \
  --deployment-name gpt-4o \
  --model-name gpt-4o \
  --model-version "2024-08-06" \
  --model-format OpenAI \
  --sku-name Standard \
  --sku-capacity 10
```

### Step 3: Get Endpoint

```bash
# Get endpoint URL
az cognitiveservices account show \
  --name $AOAI_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.endpoint -o tsv

# Output: https://your-openai.openai.azure.com/
```

### Step 4: Assign RBAC Role

```bash
# Get your OID
YOUR_OID=$(az ad signed-in-user show --query id -o tsv)

# Get resource ID
AOAI_ID=$(az cognitiveservices account show \
  --name $AOAI_NAME \
  --resource-group $RESOURCE_GROUP \
  --query id -o tsv)

# Assign Cognitive Services OpenAI User role
az role assignment create \
  --assignee "$YOUR_OID" \
  --role "Cognitive Services OpenAI User" \
  --scope "$AOAI_ID"
```

### Step 5: Configure the Framework

```toml
# config/agent.toml
[agent.azure_openai]
endpoint = "https://your-openai.openai.azure.com/"
deployment = "gpt-4o"
api_version = "2024-10-01-preview"
```

Or via environment variables:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-openai.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"
export AZURE_OPENAI_API_VERSION="2024-10-01-preview"
```

## Authentication

All Azure services use `DefaultAzureCredential`, which tries these methods in order:

1. **Environment variables** (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`)
2. **Managed Identity** (in Azure VMs, App Service, Functions)
3. **Azure CLI** (`az login`)
4. **Azure PowerShell** (`Connect-AzAccount`)
5. **Visual Studio Code** (Azure extension)
6. **Interactive browser** (fallback)

### Local Development

```bash
# Login to Azure CLI
az login

# Optionally set a specific subscription
az account set --subscription "Your Subscription Name"
```

### Production (Managed Identity)

1. Enable Managed Identity on your Azure resource (VM, App Service, etc.)
2. Assign RBAC roles to the Managed Identity
3. `DefaultAzureCredential` automatically uses it

### Service Principal

```bash
# Create service principal
az ad sp create-for-rbac \
  --name "ai-assistant-sp" \
  --role contributor \
  --scopes /subscriptions/<subscription-id>

# Set environment variables
export AZURE_CLIENT_ID="<app-id>"
export AZURE_TENANT_ID="<tenant-id>"
export AZURE_CLIENT_SECRET="<password>"
```

## Complete Configuration Example

```toml
# config/agent.toml

[agent]
system_prompt = "config/system_prompt.txt"
log_level = "INFO"

# Azure OpenAI
[agent.azure_openai]
endpoint = "https://your-openai.openai.azure.com/"
deployment = "gpt-4o"
api_version = "2024-10-01-preview"

# Redis Cache
[agent.memory.cache]
enabled = true
host = "your-redis.redis.cache.windows.net"
port = 6380
ssl = true
ttl = 3600
prefix = "chat:"

# ADLS Persistence
[agent.memory.persistence]
enabled = true
account_name = "yourstorageaccount"
container = "chat-history"
folder = "threads"
schedule = "ttl+300"

# Tool Loading
[agent.tools]
config_dir = "config/tools"
tool_modules = ["src.example_tool.tools"]
```

## Troubleshooting

### Check Authentication

```python
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()

# Test Azure OpenAI access
token = credential.get_token("https://cognitiveservices.azure.com/.default")
print(f"OpenAI token acquired: {len(token.token)} chars")

# Test Redis access
token = credential.get_token("https://redis.azure.com/.default")
print(f"Redis token acquired: {len(token.token)} chars")

# Test Storage access
token = credential.get_token("https://storage.azure.com/.default")
print(f"Storage token acquired: {len(token.token)} chars")
```

### RBAC Propagation Delay

Role assignments can take 5-15 minutes to propagate. If you get permission errors
immediately after assigning a role, wait and retry.

### Check Role Assignments

```bash
# List your role assignments
az role assignment list \
  --assignee $(az ad signed-in-user show --query id -o tsv) \
  --output table
```

### Check Redis Data Access Policies

```bash
# List data access policy assignments
az redis access-policy-assignment list \
  --redis-cache-name $REDIS_NAME \
  --resource-group $RESOURCE_GROUP \
  --output table
```
