# Memory & Session Management Guide

Multi-tier memory system with Redis cache and ADLS persistence.

## Overview

The framework provides a three-tier memory architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    Memory Tiers                         │
├─────────────────────────────────────────────────────────┤
│  Tier 1: In-Memory (active sessions)                    │
│  ├── ChatSession objects                                │
│  └── Thread references                                  │
├─────────────────────────────────────────────────────────┤
│  Tier 2: Redis Cache (fast access, TTL-based)           │
│  ├── Azure Cache for Redis with AAD auth                │
│  ├── Configurable TTL (default 1 hour)                  │
│  └── Automatic fallback to in-memory                    │
├─────────────────────────────────────────────────────────┤
│  Tier 3: ADLS Persistence (long-term storage)           │
│  ├── Azure Data Lake Storage Gen2                       │
│  ├── Scheduled persistence before TTL expiry            │
│  └── Merge logic preserves history                      │
└─────────────────────────────────────────────────────────┘
```

## Configuration

### TOML Configuration

```toml
[agent.memory]
enabled = true

# Redis Cache (Azure Cache for Redis with AAD auth)
[agent.memory.cache]
enabled = true
host = "your-redis.redis.cache.windows.net"
port = 6380
ssl = true
ttl = 3600          # 1 hour
prefix = "chat:"
database = 0

# ADLS Persistence (Azure Data Lake Storage Gen2)
[agent.memory.persistence]
enabled = true
account_name = "yourstorageaccount"
container = "chat-history"
folder = "threads"
schedule = "ttl+300"  # Persist 5 min before cache TTL expires

# Context Summarization
[agent.memory.summarization]
enabled = true
max_tokens = 8000           # Trigger summarization above this
summary_target_tokens = 2000  # Target summary size
recent_messages_to_keep = 5   # Keep recent messages after summarizing
```

## Cache Layer (Redis)

### Features

- **Azure Cache for Redis** with AAD authentication (no API keys)
- **Automatic fallback** to in-memory cache if Redis unavailable
- **TTL-based expiration** with configurable duration
- **Key prefix** for multi-tenant isolation

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `false` | Enable Redis caching |
| `host` | - | Redis host (e.g., `*.redis.cache.windows.net`) |
| `port` | `6380` | Redis port (6380 for SSL) |
| `ssl` | `true` | Use SSL/TLS connection |
| `ttl` | `3600` | Time-to-live in seconds |
| `prefix` | `"chat:"` | Key prefix for namespacing |
| `database` | `0` | Redis database number |

### Authentication

The cache uses `DefaultAzureCredential` for AAD authentication:

```python
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
# Extracts OID from token for Redis username
```

**Important:** Standard RBAC roles (`Redis Cache Contributor`) are NOT sufficient.
You must create a **Data Access Policy** assignment. See [azure-setup.md](azure-setup.md).

### Fallback Behavior

If Redis is unavailable, the cache falls back to in-memory storage:

```python
# Cache initialization
if config.cache.enabled:
    self._cache = RedisCache(config.cache)
    # If connection fails, falls back to InMemoryCache
else:
    self._cache = InMemoryCache(ttl=config.cache.ttl)
```

## Persistence Layer (ADLS)

### Features

- **Azure Blob Storage API** (works with any storage account, HNS not required)
- **Scheduled persistence** before cache TTL expiry
- **Merge logic** preserves history across sessions
- **AAD authentication** via DefaultAzureCredential

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `false` | Enable ADLS persistence |
| `account_name` | - | Azure Storage account name |
| `container` | `"chat-history"` | Blob container name |
| `folder` | `"threads"` | Folder path within container |
| `schedule` | `"ttl+300"` | When to persist (seconds before TTL) |

### Schedule Formats

| Format | Meaning |
|--------|---------|
| `"ttl+300"` | 300 seconds before cache TTL expires |
| `"ttl+600"` | 600 seconds (10 min) before TTL |
| `"300"` | Every 300 seconds (5 min) |

### Merge Logic

When persisting to ADLS, existing data is merged:

1. Load existing ADLS data (if any)
2. Merge messages (new data takes precedence)
3. Preserve original `_created_at` timestamp
4. Increment `_merge_count` for auditing
5. Save merged result

```python
# Metadata added during persistence
{
    "_created_at": "2025-01-15T10:00:00Z",
    "_updated_at": "2025-01-15T11:30:00Z",
    "_persisted": true,
    "_persisted_at": "2025-01-15T11:30:00Z",
    "_merge_count": 3,
    "_message_count": 15,
    "messages": [...]
}
```

## Context Summarization

### Purpose

Long conversations can exceed LLM context limits. Summarization compresses
older messages while preserving context.

### How It Works

1. Check if estimated tokens exceed `max_tokens`
2. Split messages into "old" (to summarize) and "recent" (to keep)
3. Generate summary using LLM
4. Create new thread with summary + recent messages
5. Save to cache

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `true` | Enable auto-summarization |
| `max_tokens` | `8000` | Token limit before summarization |
| `summary_target_tokens` | `2000` | Target size for summary |
| `recent_messages_to_keep` | `5` | Messages to preserve after summary |

### Manual Summarization

```python
# Check if summarization needed
if await history_manager.needs_summarization(chat_id):
    await history_manager.summarize_if_needed(chat_id)

# Get session stats
stats = await history_manager.get_session_stats(chat_id)
print(f"Tokens: {stats['estimated_tokens']}/{stats['max_tokens']}")
print(f"Needs summarization: {stats['needs_summarization']}")
```

## Session Lifecycle

### Session Flow

```
1. User sends question with optional chat_id
   ↓
2. ChatHistoryManager.get_or_create_thread(chat_id)
   ├── chat_id is None → Generate UUID, create new thread
   ├── chat_id in cache → Restore from Redis
   ├── chat_id in ADLS → Load from ADLS, cache it
   └── chat_id not found → Create new with provided ID
   ↓
3. Process question with thread
   ↓
4. ChatHistoryManager.save_thread(chat_id, thread)
   ├── Save to cache (Redis or in-memory)
   └── If no cache available → Persist to ADLS
   ↓
5. Background task persists before TTL expiry
```

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| `chat_id=None` | Generate new UUID, create thread |
| `chat_id` in cache | Restore from cache |
| `chat_id` not in cache, in ADLS | Load from ADLS, cache it |
| `chat_id` not found anywhere | Create new with provided ID |
| Cache unavailable | Fall back to in-memory |
| ADLS unavailable | Log warning, continue without persistence |

## API Usage

### Basic Usage

```python
async with AIAssistant() as assistant:
    # First message (new session)
    result1 = await assistant.process_question("My name is Alice")
    chat_id = result1.chat_id  # Save for continuity

    # Continue session
    result2 = await assistant.process_question(
        "What's my name?",
        chat_id=chat_id
    )
    # Response: "Your name is Alice"
```

### List Sessions

```python
chats = await assistant.list_chats(source="all", limit=100)
for chat in chats:
    print(f"{chat.chat_id}: {chat.message_count} messages, active={chat.active}")
```

### Delete Session

```python
await assistant.delete_chat(chat_id)
```

### Session Statistics

```python
stats = await assistant._history_manager.get_session_stats(chat_id)
# {
#   "chat_id": "abc-123",
#   "created_at": "2025-01-15T10:00:00Z",
#   "last_accessed": "2025-01-15T11:30:00Z",
#   "message_count": 15,
#   "estimated_tokens": 3500,
#   "max_tokens": 8000,
#   "needs_summarization": false,
#   "summarized": false,
#   "summary_count": 0,
#   "persisted": true
# }
```

## Background Persistence

The ChatHistoryManager runs a background task to persist sessions before TTL expiry:

```python
# Started automatically during AIAssistant.initialize()
await history_manager.start_background_persist()

# Stopped during AIAssistant.close()
# Also persists all active sessions before closing
await history_manager.close()
```

### Persistence Schedule

With `schedule = "ttl+300"` and `ttl = 3600`:
- Cache TTL: 3600 seconds (1 hour)
- Persist at: 3300 seconds (55 minutes into TTL)
- Check interval: ~60 seconds

## MCP Session Management

For stateful MCP servers (like databases), sessions are tracked per chat_id:

```python
# Session metadata stored in ChatSession
session.mcp_sessions = {
    "database": "mcp-session-123",
    "filesystem": "mcp-session-456"
}
```

See `src/mcp/session.py` for MCP session management details.

## Programmatic Configuration

```python
from src.memory import ChatHistoryManager, MemoryConfig, parse_memory_config
from src.memory.cache import CacheConfig
from src.memory.persistence import PersistenceConfig

# Option 1: Direct configuration
config = MemoryConfig(
    cache=CacheConfig(
        enabled=True,
        host="your-redis.redis.cache.windows.net",
        port=6380,
        ssl=True,
        ttl=3600,
    ),
    persistence=PersistenceConfig(
        enabled=True,
        account_name="yourstorage",
        container="chat-history",
        folder="threads",
    ),
)

# Option 2: Parse from TOML dict
config = parse_memory_config(toml_config["agent"])

# Create manager
manager = ChatHistoryManager(config)
```

## Troubleshooting

### Redis Connection Issues

```
Error: Redis connection failed
```

1. Verify Redis host is accessible
2. Check Data Access Policy is configured (not just RBAC)
3. Ensure `DefaultAzureCredential` has valid token
4. Check if SSL is required (`ssl = true`)

### ADLS Permission Issues

```
Error: ADLS access denied
```

1. Verify `Storage Blob Data Contributor` role is assigned
2. Check storage account name and container exist
3. Ensure `DefaultAzureCredential` has valid token

### Summarization Not Triggering

1. Check `summarization.enabled = true`
2. Verify `max_tokens` threshold is reasonable
3. Check if session has enough messages to summarize

### Session Not Persisting

1. Check `persistence.enabled = true`
2. Verify ADLS connection works
3. Check `schedule` format is correct
4. Ensure background task is running (`start_background_persist()`)
