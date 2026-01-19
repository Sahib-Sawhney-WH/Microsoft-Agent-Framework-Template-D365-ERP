"""
Tests for MCP Session Management.

Covers:
- Session creation and retrieval
- Cache and persistence integration
- Form context management
- Session lifecycle
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
import asyncio


# ==================== Test Fixtures ====================

@pytest.fixture
def mock_cache():
    """Mock Redis cache."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def mock_persistence():
    """Mock ADLS persistence."""
    persistence = AsyncMock()
    persistence.get = AsyncMock(return_value=None)
    persistence.save = AsyncMock(return_value=True)
    persistence.delete = AsyncMock(return_value=True)
    return persistence


@pytest.fixture
def session_config():
    """Sample session configuration."""
    from src.mcp.session import MCPSessionConfig
    return MCPSessionConfig(
        enabled=True,
        session_ttl=3600,
        persist_sessions=True,
        cache_prefix="mcp_session:",
    )


@pytest.fixture
def session_manager(mock_cache, mock_persistence, session_config):
    """Create session manager with mocked dependencies."""
    from src.mcp.session import MCPSessionManager
    return MCPSessionManager(
        cache=mock_cache,
        persistence=mock_persistence,
        config=session_config,
    )


# ==================== MCPSessionState Tests ====================

class TestMCPSessionState:
    """Tests for MCPSessionState dataclass."""

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        from src.mcp.session import MCPSessionState

        session = MCPSessionState(
            session_id="session-123",
            chat_id="chat-456",
            mcp_server_name="d365-erp",
            user_id="user@example.com",
            form_context={"SalesOrder": {"quantity": 100}},
        )

        data = session.to_dict()

        assert data["session_id"] == "session-123"
        assert data["chat_id"] == "chat-456"
        assert data["mcp_server_name"] == "d365-erp"
        assert data["user_id"] == "user@example.com"
        assert data["form_context"]["SalesOrder"]["quantity"] == 100
        assert "created_at" in data
        assert "last_accessed" in data

    def test_from_dict_deserialization(self):
        """Test deserialization from dictionary."""
        from src.mcp.session import MCPSessionState

        data = {
            "session_id": "session-123",
            "chat_id": "chat-456",
            "mcp_server_name": "d365-erp",
            "user_id": "user@example.com",
            "form_context": {"SalesOrder": {"quantity": 100}},
            "created_at": "2025-01-15T10:00:00+00:00",
            "last_accessed": "2025-01-15T11:00:00+00:00",
            "metadata": {"custom": "value"},
        }

        session = MCPSessionState.from_dict(data)

        assert session.session_id == "session-123"
        assert session.chat_id == "chat-456"
        assert session.mcp_server_name == "d365-erp"
        assert session.user_id == "user@example.com"
        assert session.form_context["SalesOrder"]["quantity"] == 100
        assert session.metadata["custom"] == "value"

    def test_from_dict_handles_missing_optional_fields(self):
        """Test deserialization handles missing optional fields."""
        from src.mcp.session import MCPSessionState

        data = {
            "session_id": "session-123",
            "chat_id": "chat-456",
            "mcp_server_name": "d365-erp",
            "created_at": "2025-01-15T10:00:00+00:00",
            "last_accessed": "2025-01-15T11:00:00+00:00",
        }

        session = MCPSessionState.from_dict(data)

        assert session.user_id is None
        assert session.form_context == {}
        assert session.metadata == {}


# ==================== MCPSessionManager Tests ====================

class TestMCPSessionManager:
    """Tests for MCPSessionManager class."""

    @pytest.mark.asyncio
    async def test_get_or_create_session_creates_new(self, session_manager):
        """Test creating a new session when none exists."""
        session = await session_manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
            user_id="user@example.com",
        )

        assert session is not None
        assert session.chat_id == "chat-123"
        assert session.mcp_server_name == "d365-erp"
        assert session.user_id == "user@example.com"
        assert session.session_id is not None

    @pytest.mark.asyncio
    async def test_get_or_create_session_returns_cached(self, session_manager):
        """Test returning cached session on subsequent calls."""
        session1 = await session_manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
        )

        session2 = await session_manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
        )

        assert session1.session_id == session2.session_id

    @pytest.mark.asyncio
    async def test_get_or_create_session_loads_from_cache(
        self, mock_cache, mock_persistence, session_config
    ):
        """Test loading session from cache."""
        from src.mcp.session import MCPSessionManager

        cached_data = {
            "session_id": "cached-session-123",
            "chat_id": "chat-123",
            "mcp_server_name": "d365-erp",
            "created_at": "2025-01-15T10:00:00+00:00",
            "last_accessed": "2025-01-15T11:00:00+00:00",
        }
        mock_cache.get = AsyncMock(return_value=cached_data)

        manager = MCPSessionManager(
            cache=mock_cache,
            persistence=mock_persistence,
            config=session_config,
        )

        session = await manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
        )

        assert session.session_id == "cached-session-123"

    @pytest.mark.asyncio
    async def test_get_or_create_session_loads_from_persistence(
        self, mock_cache, mock_persistence, session_config
    ):
        """Test loading session from persistence when not in cache."""
        from src.mcp.session import MCPSessionManager

        persisted_data = {
            "session_id": "persisted-session-123",
            "chat_id": "chat-123",
            "mcp_server_name": "d365-erp",
            "created_at": "2025-01-15T10:00:00+00:00",
            "last_accessed": "2025-01-15T11:00:00+00:00",
        }
        mock_cache.get = AsyncMock(return_value=None)  # Not in cache
        mock_persistence.get = AsyncMock(return_value=persisted_data)

        manager = MCPSessionManager(
            cache=mock_cache,
            persistence=mock_persistence,
            config=session_config,
        )

        session = await manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
        )

        assert session.session_id == "persisted-session-123"
        # Should also warm up cache
        mock_cache.set.assert_called()

    @pytest.mark.asyncio
    async def test_save_session(self, session_manager, mock_cache, mock_persistence):
        """Test saving session to cache and persistence."""
        from src.mcp.session import MCPSessionState

        session = MCPSessionState(
            session_id="session-123",
            chat_id="chat-456",
            mcp_server_name="d365-erp",
        )

        await session_manager.save_session(session, persist=True)

        mock_cache.set.assert_called()
        mock_persistence.save.assert_called()

    @pytest.mark.asyncio
    async def test_update_form_context(self, session_manager):
        """Test updating form context within a session."""
        session = await session_manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
        )

        result = await session_manager.update_form_context(
            session_id=session.session_id,
            form_name="SalesOrder",
            field_data={"quantity": 100, "customer": "ACME"},
        )

        assert result is True

        # Verify the session was updated
        updated_session = await session_manager.get_session(session.session_id)
        assert updated_session is not None
        assert "SalesOrder" in updated_session.form_context
        assert updated_session.form_context["SalesOrder"]["quantity"] == 100
        assert updated_session.form_context["_active_form"] == "SalesOrder"

    @pytest.mark.asyncio
    async def test_update_form_context_nonexistent_session(self, session_manager):
        """Test updating form context for non-existent session returns False."""
        result = await session_manager.update_form_context(
            session_id="nonexistent-session",
            form_name="SalesOrder",
            field_data={"quantity": 100},
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_clear_form_context_specific_form(self, session_manager):
        """Test clearing specific form context."""
        session = await session_manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
        )

        # Add form context
        await session_manager.update_form_context(
            session.session_id, "SalesOrder", {"quantity": 100}
        )
        await session_manager.update_form_context(
            session.session_id, "PurchaseOrder", {"vendor": "Supplier"}
        )

        # Clear specific form
        result = await session_manager.clear_form_context(
            session.session_id, form_name="SalesOrder"
        )

        assert result is True
        updated = await session_manager.get_session(session.session_id)
        assert "SalesOrder" not in updated.form_context
        assert "PurchaseOrder" in updated.form_context

    @pytest.mark.asyncio
    async def test_clear_form_context_all_forms(self, session_manager):
        """Test clearing all form context."""
        session = await session_manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
        )

        # Add form context
        await session_manager.update_form_context(
            session.session_id, "SalesOrder", {"quantity": 100}
        )

        # Clear all
        result = await session_manager.clear_form_context(session.session_id)

        assert result is True
        updated = await session_manager.get_session(session.session_id)
        assert updated.form_context == {}

    @pytest.mark.asyncio
    async def test_build_mcp_kwargs(self, session_manager):
        """Test building kwargs for MCP tool invocation."""
        from src.mcp.session import MCPSessionState

        session = MCPSessionState(
            session_id="session-123",
            chat_id="chat-456",
            mcp_server_name="d365-erp",
            user_id="user@example.com",
            form_context={"SalesOrder": {"quantity": 100}},
        )

        kwargs = session_manager.build_mcp_kwargs(session)

        assert kwargs["session_id"] == "session-123"
        assert kwargs["chat_id"] == "chat-456"
        assert kwargs["user_id"] == "user@example.com"
        assert kwargs["form_context"]["SalesOrder"]["quantity"] == 100

    @pytest.mark.asyncio
    async def test_delete_session(self, session_manager, mock_cache, mock_persistence):
        """Test deleting a session from all layers."""
        # Create session first
        await session_manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
        )

        result = await session_manager.delete_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
        )

        assert result is True
        mock_cache.delete.assert_called()
        mock_persistence.delete.assert_called()

    @pytest.mark.asyncio
    async def test_list_sessions(self, session_manager):
        """Test listing sessions."""
        # Create multiple sessions
        await session_manager.get_or_create_session(
            chat_id="chat-1", mcp_server_name="d365-erp"
        )
        await session_manager.get_or_create_session(
            chat_id="chat-2", mcp_server_name="d365-erp"
        )
        await session_manager.get_or_create_session(
            chat_id="chat-1", mcp_server_name="other-server"
        )

        # List all
        all_sessions = await session_manager.list_sessions()
        assert len(all_sessions) == 3

        # List filtered by chat_id
        chat1_sessions = await session_manager.list_sessions(chat_id="chat-1")
        assert len(chat1_sessions) == 2

    @pytest.mark.asyncio
    async def test_close_persists_sessions(
        self, mock_cache, mock_persistence, session_config
    ):
        """Test that close() persists all active sessions."""
        from src.mcp.session import MCPSessionManager

        manager = MCPSessionManager(
            cache=mock_cache,
            persistence=mock_persistence,
            config=session_config,
        )

        # Create sessions
        await manager.get_or_create_session(chat_id="chat-1", mcp_server_name="d365")
        await manager.get_or_create_session(chat_id="chat-2", mcp_server_name="d365")

        # Close manager
        await manager.close()

        # Verify persistence was called for each session
        assert mock_persistence.save.call_count >= 2


# ==================== Configuration Tests ====================

class TestMCPSessionConfig:
    """Tests for MCP session configuration parsing."""

    def test_parse_mcp_session_config(self):
        """Test parsing session configuration from dict."""
        from src.mcp.session import parse_mcp_session_config

        config_dict = {
            "mcp_sessions": {
                "enabled": True,
                "session_ttl": 7200,
                "persist_sessions": False,
                "cache_prefix": "custom:",
            }
        }

        config = parse_mcp_session_config(config_dict)

        assert config.enabled is True
        assert config.session_ttl == 7200
        assert config.persist_sessions is False
        assert config.cache_prefix == "custom:"

    def test_parse_mcp_session_config_defaults(self):
        """Test default values when config not provided."""
        from src.mcp.session import parse_mcp_session_config

        config = parse_mcp_session_config({})

        assert config.enabled is False
        assert config.session_ttl == 3600
        assert config.persist_sessions is True
        assert config.cache_prefix == "mcp_session:"
