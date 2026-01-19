"""
Tests for the memory module (cache + persistence).

Uses mocks for Redis and ADLS to test all edge cases without real infrastructure.
"""

import asyncio
import pytest
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

# Import the modules we're testing
from src.memory.cache import RedisCache, InMemoryCache, CacheConfig
from src.memory.persistence import ADLSPersistence, PersistenceConfig
from src.memory.manager import ChatHistoryManager, MemoryConfig, parse_memory_config


# =============================================================================
# Mock Classes for Testing
# =============================================================================

class MockRedisClient:
    """Mock Redis client for testing without real Redis."""
    
    def __init__(self):
        self._store: Dict[str, str] = {}
        self._ttls: Dict[str, int] = {}
    
    async def ping(self):
        return True
    
    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)
    
    async def setex(self, key: str, ttl: int, value: str):
        self._store[key] = value
        self._ttls[key] = ttl
    
    async def delete(self, key: str):
        self._store.pop(key, None)
        self._ttls.pop(key, None)
    
    async def ttl(self, key: str) -> int:
        return self._ttls.get(key, -2)
    
    async def keys(self, pattern: str):
        # Simple pattern matching (just prefix)
        prefix = pattern.replace("*", "")
        return [k for k in self._store.keys() if k.startswith(prefix)]
    
    async def exists(self, key: str) -> bool:
        return key in self._store
    
    async def expire(self, key: str, ttl: int):
        if key in self._store:
            self._ttls[key] = ttl
    
    def pipeline(self):
        return MockRedisPipeline(self)
    
    async def close(self):
        pass


class MockRedisPipeline:
    """Mock Redis pipeline for testing."""
    
    def __init__(self, client: MockRedisClient):
        self._client = client
        self._commands = []
    
    def exists(self, key: str):
        self._commands.append(("exists", key))
        return self
    
    def ttl(self, key: str):
        self._commands.append(("ttl", key))
        return self
    
    async def execute(self):
        results = []
        for cmd, key in self._commands:
            if cmd == "exists":
                results.append(key in self._client._store)
            elif cmd == "ttl":
                results.append(self._client._ttls.get(key, -2))
        return results


class MockADLSFileClient:
    """Mock ADLS file client for testing."""
    
    def __init__(self, container: "MockADLSContainer", path: str):
        self._container = container
        self._path = path
    
    async def download_file(self):
        if self._path not in self._container._files:
            raise Exception("PathNotFound")
        return MockADLSDownload(self._container._files[self._path])
    
    async def upload_data(self, data: bytes, overwrite: bool = True, metadata: dict = None):
        self._container._files[self._path] = data
        self._container._metadata[self._path] = metadata or {}
    
    async def delete_file(self):
        self._container._files.pop(self._path, None)
        self._container._metadata.pop(self._path, None)
    
    async def get_file_properties(self):
        if self._path not in self._container._files:
            raise Exception("PathNotFound")
        return MagicMock(
            size=len(self._container._files[self._path]),
            last_modified=datetime.now(timezone.utc),
            metadata=self._container._metadata.get(self._path, {})
        )


class MockADLSDownload:
    """Mock ADLS download for testing."""
    
    def __init__(self, data: bytes):
        self._data = data
    
    async def readall(self) -> bytes:
        return self._data


class MockADLSContainer:
    """Mock ADLS container client for testing."""
    
    def __init__(self):
        self._files: Dict[str, bytes] = {}
        self._metadata: Dict[str, dict] = {}
    
    async def get_file_system_properties(self):
        return MagicMock()
    
    async def create_file_system(self):
        pass
    
    def get_file_client(self, path: str):
        return MockADLSFileClient(self, path)
    
    async def get_paths(self, path: str = ""):
        for file_path in self._files.keys():
            if file_path.startswith(path):
                yield MagicMock(
                    name=file_path,
                    content_length=len(self._files[file_path]),
                    last_modified=datetime.now(timezone.utc)
                )


class MockAgent:
    """Mock ChatAgent for testing thread operations."""
    
    def __init__(self):
        self._threads: Dict[str, Dict] = {}
    
    def get_new_thread(self):
        thread_id = f"thread_{len(self._threads)}"
        thread = MockThread(thread_id)
        return thread
    
    async def deserialize_thread(self, data: Dict) -> "MockThread":
        thread = MockThread(data.get("id", "restored"))
        thread._messages = data.get("messages", [])
        return thread
    
    async def run(self, message: str, thread: "MockThread" = None):
        if thread:
            thread._messages.append({"role": "user", "content": message})
            thread._messages.append({"role": "assistant", "content": f"Response to: {message}"})
        return MagicMock(text=f"Response to: {message}")


class MockThread:
    """Mock agent thread for testing."""
    
    def __init__(self, thread_id: str):
        self.id = thread_id
        self._messages = []
    
    async def serialize(self) -> Dict:
        return {
            "id": self.id,
            "messages": self._messages,
            "_created_at": datetime.now(timezone.utc).isoformat()
        }


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def cache_config():
    return CacheConfig(
        enabled=True,
        host="test-redis.redis.cache.windows.net",
        port=6380,
        ssl=True,
        ttl=3600,
        prefix="chat:",
        database=0
    )


@pytest.fixture
def persistence_config():
    return PersistenceConfig(
        enabled=True,
        account_name="teststorage",
        container="chat-history",
        folder="threads",
        schedule="ttl+300"
    )


@pytest.fixture
def memory_config(cache_config, persistence_config):
    return MemoryConfig(cache=cache_config, persistence=persistence_config)


@pytest.fixture
def mock_agent():
    return MockAgent()


# =============================================================================
# InMemoryCache Tests
# =============================================================================

class TestInMemoryCache:
    """Tests for the in-memory fallback cache."""
    
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        cache = InMemoryCache(ttl=3600)
        
        await cache.set("chat1", {"messages": ["hello"]})
        result = await cache.get("chat1")
        
        assert result == {"messages": ["hello"]}
    
    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        cache = InMemoryCache(ttl=3600)
        
        result = await cache.get("nonexistent")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete(self):
        cache = InMemoryCache(ttl=3600)
        
        await cache.set("chat1", {"messages": []})
        await cache.delete("chat1")
        result = await cache.get("chat1")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_list_keys(self):
        cache = InMemoryCache(ttl=3600)
        
        await cache.set("chat1", {})
        await cache.set("chat2", {})
        
        keys = await cache.list_keys()
        
        assert set(keys) == {"chat1", "chat2"}


# =============================================================================
# RedisCache Tests (with mocks)
# =============================================================================

class TestRedisCache:
    """Tests for Redis cache with mocked client."""
    
    @pytest.mark.asyncio
    async def test_disabled_cache_returns_none(self):
        config = CacheConfig(enabled=False)
        cache = RedisCache(config)
        
        result = await cache.get("any_id")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_set_and_get_with_mock(self, cache_config):
        cache = RedisCache(cache_config)
        cache._client = MockRedisClient()
        cache._initialized = True
        
        await cache.set("chat1", {"messages": ["test"]}, ttl=600)
        result = await cache.get("chat1")
        
        assert result == {"messages": ["test"]}
    
    @pytest.mark.asyncio
    async def test_ttl_tracking(self, cache_config):
        cache = RedisCache(cache_config)
        cache._client = MockRedisClient()
        cache._initialized = True
        
        await cache.set("chat1", {}, ttl=600)
        ttl = await cache.get_ttl("chat1")
        
        assert ttl == 600


# =============================================================================
# ADLSPersistence Tests (with mocks)
# =============================================================================

class TestADLSPersistence:
    """Tests for ADLS persistence with mocked client."""
    
    @pytest.mark.asyncio
    async def test_disabled_persistence_returns_none(self):
        config = PersistenceConfig(enabled=False)
        persistence = ADLSPersistence(config)
        
        result = await persistence.get("any_id")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_save_and_get_with_mock(self, persistence_config):
        persistence = ADLSPersistence(persistence_config)
        persistence._container_client = MockADLSContainer()
        persistence._initialized = True
        
        await persistence.save("chat1", {"messages": ["hello"]})
        result = await persistence.get("chat1")
        
        assert "messages" in result
        assert result["messages"] == ["hello"]
        assert "_persisted_at" in result
    
    @pytest.mark.asyncio
    async def test_exists(self, persistence_config):
        persistence = ADLSPersistence(persistence_config)
        persistence._container_client = MockADLSContainer()
        persistence._initialized = True
        
        assert await persistence.exists("chat1") is False
        
        await persistence.save("chat1", {"messages": []})
        
        assert await persistence.exists("chat1") is True
    
    @pytest.mark.asyncio
    async def test_delete(self, persistence_config):
        persistence = ADLSPersistence(persistence_config)
        persistence._container_client = MockADLSContainer()
        persistence._initialized = True
        
        await persistence.save("chat1", {})
        await persistence.delete("chat1")
        
        assert await persistence.exists("chat1") is False
    
    def test_parse_schedule(self, persistence_config):
        persistence = ADLSPersistence(persistence_config)
        
        # "ttl+300" with 3600 TTL should return 3300
        result = persistence.parse_schedule(3600)
        assert result == 3300
        
        # Test with different buffer
        persistence.config.schedule = "ttl+600"
        result = persistence.parse_schedule(3600)
        assert result == 3000


# =============================================================================
# ChatHistoryManager Tests
# =============================================================================

class TestChatHistoryManager:
    """Tests for the full chat history manager."""
    
    @pytest.mark.asyncio
    async def test_create_new_session_no_chat_id(self, memory_config, mock_agent):
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        # Use in-memory cache for testing
        manager._cache = InMemoryCache(ttl=3600)
        manager._persistence.config.enabled = False
        
        chat_id, thread = await manager.get_or_create_thread(None)
        
        assert chat_id is not None
        assert len(chat_id) == 36  # UUID format
        assert thread is not None
    
    @pytest.mark.asyncio
    async def test_create_session_with_provided_id(self, memory_config, mock_agent):
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        manager._cache = InMemoryCache(ttl=3600)
        manager._persistence.config.enabled = False
        
        chat_id, thread = await manager.get_or_create_thread("my-custom-id")
        
        assert chat_id == "my-custom-id"
    
    @pytest.mark.asyncio
    async def test_restore_from_cache(self, memory_config, mock_agent):
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        manager._cache = InMemoryCache(ttl=3600)
        manager._persistence.config.enabled = False
        
        # Pre-populate cache
        thread_data = {
            "id": "existing-thread",
            "messages": [{"role": "user", "content": "Hello"}],
            "_created_at": datetime.now(timezone.utc).isoformat()
        }
        await manager._cache.set("cached-session", thread_data)
        
        # Request the cached session
        chat_id, thread = await manager.get_or_create_thread("cached-session")
        
        assert chat_id == "cached-session"
        assert len(thread._messages) == 1
    
    @pytest.mark.asyncio
    async def test_restore_from_adls_when_not_in_cache(self, memory_config, mock_agent):
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        manager._cache = InMemoryCache(ttl=3600)
        
        # Setup mock ADLS
        manager._persistence._container_client = MockADLSContainer()
        manager._persistence._initialized = True
        
        # Pre-populate ADLS
        thread_data = {
            "id": "persisted-thread",
            "messages": [{"role": "user", "content": "From ADLS"}],
            "_created_at": datetime.now(timezone.utc).isoformat()
        }
        await manager._persistence.save("adls-session", thread_data)
        
        # Request the session (not in cache, but in ADLS)
        chat_id, thread = await manager.get_or_create_thread("adls-session")
        
        assert chat_id == "adls-session"
        # Thread was restored from ADLS
        assert thread is not None
        
        # Check it was also cached
        cached = await manager._cache.get("adls-session")
        assert cached is not None
    
    @pytest.mark.asyncio
    async def test_create_new_when_not_found_anywhere(self, memory_config, mock_agent):
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        manager._cache = InMemoryCache(ttl=3600)
        manager._persistence._container_client = MockADLSContainer()
        manager._persistence._initialized = True
        
        # Request a session that doesn't exist anywhere
        chat_id, thread = await manager.get_or_create_thread("nonexistent-id")
        
        # Should create new session with the provided ID
        assert chat_id == "nonexistent-id"
        assert thread is not None
    
    @pytest.mark.asyncio
    async def test_save_thread(self, memory_config, mock_agent):
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        manager._cache = InMemoryCache(ttl=3600)
        manager._persistence.config.enabled = False
        
        chat_id, thread = await manager.get_or_create_thread("save-test")
        
        # Simulate conversation
        thread._messages.append({"role": "user", "content": "Test"})
        
        # Save
        result = await manager.save_thread(chat_id, thread)
        
        assert result is True
        
        # Verify cached
        cached = await manager._cache.get("save-test")
        assert cached is not None
        assert len(cached["messages"]) == 1
    
    @pytest.mark.asyncio
    async def test_merge_on_persist(self, memory_config, mock_agent):
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        manager._cache = InMemoryCache(ttl=3600)
        manager._persistence._container_client = MockADLSContainer()
        manager._persistence._initialized = True
        
        # Pre-populate ADLS with old data
        old_data = {
            "id": "merge-test",
            "messages": [{"role": "user", "content": "Old message"}],
            "_created_at": "2025-01-01T00:00:00"
        }
        await manager._persistence.save("merge-test", old_data)
        
        # New data with more messages
        new_data = {
            "id": "merge-test",
            "messages": [
                {"role": "user", "content": "Old message"},
                {"role": "assistant", "content": "Response"},
                {"role": "user", "content": "New message"}
            ],
            "_created_at": "2025-01-01T00:00:00",
            "_updated_at": "2025-01-05T10:00:00"
        }
        
        # Persist with merge
        await manager._persist_with_merge("merge-test", new_data)
        
        # Verify merged data
        persisted = await manager._persistence.get("merge-test")
        assert persisted is not None
        assert persisted["_created_at"] == "2025-01-01T00:00:00"  # Preserved original
        assert len(persisted["messages"]) == 3
        assert persisted.get("_merge_count") == 1
    
    @pytest.mark.asyncio
    async def test_delete_chat(self, memory_config, mock_agent):
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        manager._cache = InMemoryCache(ttl=3600)
        manager._persistence._container_client = MockADLSContainer()
        manager._persistence._initialized = True
        
        # Create a session
        chat_id, thread = await manager.get_or_create_thread("delete-test")
        await manager.save_thread(chat_id, thread, force_persist=True)
        
        # Delete
        result = await manager.delete_chat("delete-test")
        
        assert result is True
        assert await manager._cache.get("delete-test") is None
        assert await manager._persistence.exists("delete-test") is False
    
    @pytest.mark.asyncio
    async def test_list_chats(self, memory_config, mock_agent):
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        manager._cache = InMemoryCache(ttl=3600)
        manager._persistence._container_client = MockADLSContainer()
        manager._persistence._initialized = True
        
        # Create some sessions
        await manager.get_or_create_thread("chat1")
        await manager.get_or_create_thread("chat2")
        
        # List
        chats = await manager.list_chats()
        
        assert len(chats) >= 2
        chat_ids = [c["chat_id"] for c in chats]
        assert "chat1" in chat_ids
        assert "chat2" in chat_ids


# =============================================================================
# Config Parsing Tests
# =============================================================================

class TestConfigParsing:
    """Tests for parsing memory config from TOML."""
    
    def test_parse_full_config(self):
        config_dict = {
            "memory": {
                "cache": {
                    "enabled": True,
                    "host": "my-redis.redis.cache.windows.net",
                    "port": 6380,
                    "ssl": True,
                    "ttl": 7200,
                    "prefix": "session:",
                    "database": 1
                },
                "persistence": {
                    "enabled": True,
                    "account_name": "mystorageaccount",
                    "container": "chats",
                    "folder": "history",
                    "schedule": "ttl+600"
                }
            }
        }
        
        result = parse_memory_config(config_dict)
        
        assert result.cache.enabled is True
        assert result.cache.host == "my-redis.redis.cache.windows.net"
        assert result.cache.ttl == 7200
        assert result.cache.prefix == "session:"
        
        assert result.persistence.enabled is True
        assert result.persistence.account_name == "mystorageaccount"
        assert result.persistence.container == "chats"
        assert result.persistence.schedule == "ttl+600"
    
    def test_parse_empty_config(self):
        config_dict = {}
        
        result = parse_memory_config(config_dict)
        
        # Should use defaults
        assert result.cache.enabled is False
        assert result.persistence.enabled is False
    
    def test_parse_partial_config(self):
        config_dict = {
            "memory": {
                "cache": {
                    "enabled": True,
                    "host": "test-redis.redis.cache.windows.net"
                    # Missing other fields - should use defaults
                }
            }
        }
        
        result = parse_memory_config(config_dict)
        
        assert result.cache.enabled is True
        assert result.cache.host == "test-redis.redis.cache.windows.net"
        assert result.cache.port == 6380  # Default
        assert result.cache.ttl == 3600  # Default


# =============================================================================
# Integration Tests (Full Flow)
# =============================================================================

class TestIntegrationFlow:
    """Integration tests for the complete flow."""
    
    @pytest.mark.asyncio
    async def test_full_conversation_flow(self, memory_config, mock_agent):
        """Test a complete conversation with cache and persistence."""
        manager = ChatHistoryManager(memory_config)
        manager.set_agent(mock_agent)
        manager._cache = InMemoryCache(ttl=3600)
        manager._persistence._container_client = MockADLSContainer()
        manager._persistence._initialized = True
        
        # First message - new session
        chat_id, thread = await manager.get_or_create_thread(None)
        thread._messages.append({"role": "user", "content": "Hello"})
        thread._messages.append({"role": "assistant", "content": "Hi there!"})
        await manager.save_thread(chat_id, thread)
        
        # Second message - same session
        chat_id2, thread2 = await manager.get_or_create_thread(chat_id)
        assert chat_id2 == chat_id
        thread2._messages.append({"role": "user", "content": "How are you?"})
        thread2._messages.append({"role": "assistant", "content": "I'm doing well!"})
        await manager.save_thread(chat_id2, thread2, force_persist=True)
        
        # Clear cache to simulate restart
        await manager._cache.delete(chat_id)
        
        # Should restore from ADLS
        chat_id3, thread3 = await manager.get_or_create_thread(chat_id)
        assert chat_id3 == chat_id
        assert len(thread3._messages) == 4
        
        # Cleanup
        await manager.close()


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
