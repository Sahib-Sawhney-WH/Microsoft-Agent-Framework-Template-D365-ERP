"""
MCP Session Management.

Manages stateful MCP sessions for servers like D365 ERP that require
session continuity across tool invocations.

Features:
- Session creation and retrieval
- Cache and persistence layer integration
- Form context management for D365
- Kwargs building for MCP tool invocation
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.memory.cache import RedisCache, InMemoryCache
    from src.memory.persistence import ADLSPersistence

logger = structlog.get_logger(__name__)


@dataclass
class MCPSessionConfig:
    """Configuration for MCP session management."""

    enabled: bool = False
    session_ttl: int = 3600  # Session TTL in seconds
    persist_sessions: bool = True  # Persist to ADLS
    cache_prefix: str = "mcp_session:"


@dataclass
class MCPSessionState:
    """
    Represents the state of an MCP session.

    Used to maintain continuity with stateful MCP servers like D365 ERP.

    Attributes:
        session_id: Unique identifier for this MCP session
        chat_id: Links to the chat history session
        mcp_server_name: Name of the MCP server this session is for
        user_id: Optional user identifier
        form_context: D365 form state and field data
        created_at: When the session was created
        last_accessed: Last access timestamp
        metadata: Additional session metadata
    """

    session_id: str
    chat_id: str
    mcp_server_name: str
    user_id: Optional[str] = None
    form_context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "chat_id": self.chat_id,
            "mcp_server_name": self.mcp_server_name,
            "user_id": self.user_id,
            "form_context": self.form_context,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPSessionState":
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            chat_id=data["chat_id"],
            mcp_server_name=data["mcp_server_name"],
            user_id=data.get("user_id"),
            form_context=data.get("form_context", {}),
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data.get("created_at"), str)
            else data.get("created_at", datetime.now(timezone.utc)),
            last_accessed=datetime.fromisoformat(data["last_accessed"])
            if isinstance(data.get("last_accessed"), str)
            else data.get("last_accessed", datetime.now(timezone.utc)),
            metadata=data.get("metadata", {}),
        )


class MCPSessionManager:
    """
    Manages stateful MCP sessions for D365 ERP and similar servers.

    Handles session lifecycle including:
    - Creation and retrieval
    - Cache layer (Redis) for fast access
    - Persistence layer (ADLS) for durability
    - Form context management for D365 workflows

    Usage:
        manager = MCPSessionManager(cache, persistence, config)

        # Get or create a session
        session = await manager.get_or_create_session(
            chat_id="chat-123",
            mcp_server_name="d365-erp",
            user_id="user@example.com"
        )

        # Build kwargs for MCP tool invocation
        kwargs = manager.build_mcp_kwargs(session)

        # Update form context after D365 interaction
        await manager.update_form_context(
            session.session_id,
            "SalesOrder",
            {"quantity": 100, "customer": "ACME"}
        )
    """

    def __init__(
        self,
        cache: Optional[Any] = None,
        persistence: Optional[Any] = None,
        config: Optional[MCPSessionConfig] = None,
    ):
        """
        Initialize the MCP session manager.

        Args:
            cache: Redis or InMemory cache instance
            persistence: ADLS persistence instance
            config: MCPSessionConfig instance
        """
        self._cache = cache
        self._persistence = persistence
        self._config = config or MCPSessionConfig()
        self._sessions: Dict[str, MCPSessionState] = {}

        logger.info(
            "MCPSessionManager initialized",
            enabled=self._config.enabled,
            persist=self._config.persist_sessions,
        )

    def _cache_key(self, chat_id: str, mcp_server_name: str) -> str:
        """Generate cache key for a session."""
        return f"{self._config.cache_prefix}{chat_id}:{mcp_server_name}"

    async def get_or_create_session(
        self,
        chat_id: str,
        mcp_server_name: str,
        user_id: Optional[str] = None,
    ) -> MCPSessionState:
        """
        Get existing or create new MCP session.

        Lookup order:
        1. In-memory cache
        2. Redis cache
        3. ADLS persistence
        4. Create new session

        Args:
            chat_id: The chat session ID to link to
            mcp_server_name: Name of the MCP server
            user_id: Optional user identifier

        Returns:
            MCPSessionState for this chat/server combination
        """
        cache_key = self._cache_key(chat_id, mcp_server_name)

        # Check in-memory first
        if cache_key in self._sessions:
            session = self._sessions[cache_key]
            session.last_accessed = datetime.now(timezone.utc)
            logger.debug("Found session in memory", session_id=session.session_id)
            return session

        # Try cache (Redis)
        if self._cache:
            try:
                cached = await self._cache.get(cache_key)
                if cached:
                    session = MCPSessionState.from_dict(cached)
                    session.last_accessed = datetime.now(timezone.utc)
                    self._sessions[cache_key] = session
                    logger.debug("Found session in cache", session_id=session.session_id)
                    return session
            except Exception as e:
                logger.warning("Cache lookup failed", error=str(e))

        # Try persistence (ADLS)
        if self._persistence and self._config.persist_sessions:
            try:
                persisted = await self._persistence.get(cache_key)
                if persisted:
                    session = MCPSessionState.from_dict(persisted)
                    session.last_accessed = datetime.now(timezone.utc)
                    self._sessions[cache_key] = session
                    # Warm up cache
                    if self._cache:
                        await self._cache.set(cache_key, session.to_dict(), ttl=self._config.session_ttl)
                    logger.debug("Found session in persistence", session_id=session.session_id)
                    return session
            except Exception as e:
                logger.warning("Persistence lookup failed", error=str(e))

        # Create new session
        session = MCPSessionState(
            session_id=str(uuid.uuid4()),
            chat_id=chat_id,
            mcp_server_name=mcp_server_name,
            user_id=user_id,
            form_context={},
            created_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
            metadata={},
        )

        # Save the new session
        await self.save_session(session, persist=self._config.persist_sessions)

        logger.info(
            "Created new MCP session",
            session_id=session.session_id,
            chat_id=chat_id,
            mcp_server=mcp_server_name,
        )

        return session

    async def get_session(self, session_id: str) -> Optional[MCPSessionState]:
        """
        Get a session by its session_id.

        Args:
            session_id: The session ID to look up

        Returns:
            MCPSessionState or None if not found
        """
        # Search in memory
        for session in self._sessions.values():
            if session.session_id == session_id:
                return session

        # Would need to search cache/persistence by session_id
        # This is less efficient, so prefer using chat_id + mcp_server_name
        logger.debug("Session not found by session_id", session_id=session_id)
        return None

    async def save_session(
        self,
        session: MCPSessionState,
        persist: bool = False,
    ) -> None:
        """
        Save session state to cache and optionally persistence.

        Args:
            session: The session to save
            persist: If True, also save to ADLS
        """
        cache_key = self._cache_key(session.chat_id, session.mcp_server_name)
        session.last_accessed = datetime.now(timezone.utc)
        session_dict = session.to_dict()

        # Save to memory
        self._sessions[cache_key] = session

        # Save to cache
        if self._cache:
            try:
                await self._cache.set(cache_key, session_dict, ttl=self._config.session_ttl)
            except Exception as e:
                logger.warning("Failed to cache session", error=str(e))

        # Save to persistence
        if persist and self._persistence:
            try:
                await self._persistence.save(cache_key, session_dict)
                logger.debug("Persisted session", session_id=session.session_id)
            except Exception as e:
                logger.warning("Failed to persist session", error=str(e))

    async def update_form_context(
        self,
        session_id: str,
        form_name: str,
        field_data: Dict[str, Any],
    ) -> bool:
        """
        Update D365 form context within a session.

        Used to track form state during D365 ERP interactions.

        Args:
            session_id: The session ID to update
            form_name: Name of the D365 form (e.g., "SalesOrder")
            field_data: Dictionary of field values

        Returns:
            True if update successful
        """
        session = await self.get_session(session_id)
        if not session:
            logger.warning("Session not found for form context update", session_id=session_id)
            return False

        # Update form context
        if form_name not in session.form_context:
            session.form_context[form_name] = {}

        session.form_context[form_name].update(field_data)
        session.form_context["_active_form"] = form_name
        session.form_context["_last_update"] = datetime.now(timezone.utc).isoformat()

        # Save updated session
        await self.save_session(session, persist=self._config.persist_sessions)

        logger.debug(
            "Updated form context",
            session_id=session_id,
            form_name=form_name,
            field_count=len(field_data),
        )

        return True

    async def clear_form_context(
        self,
        session_id: str,
        form_name: Optional[str] = None,
    ) -> bool:
        """
        Clear form context for a session.

        Args:
            session_id: The session ID
            form_name: Optional specific form to clear (clears all if None)

        Returns:
            True if successful
        """
        session = await self.get_session(session_id)
        if not session:
            return False

        if form_name:
            session.form_context.pop(form_name, None)
            if session.form_context.get("_active_form") == form_name:
                session.form_context.pop("_active_form", None)
        else:
            session.form_context = {}

        await self.save_session(session, persist=self._config.persist_sessions)
        return True

    def build_mcp_kwargs(self, session: MCPSessionState) -> Dict[str, Any]:
        """
        Build kwargs dictionary for MCP tool invocation.

        The SDK passes custom kwargs through to MCP calls, allowing
        session context to be included in requests.

        Args:
            session: The session to build kwargs from

        Returns:
            Dictionary of kwargs to pass to MCP tool
        """
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "form_context": session.form_context,
            "chat_id": session.chat_id,
        }

    async def delete_session(
        self,
        chat_id: str,
        mcp_server_name: str,
    ) -> bool:
        """
        Delete a session from all storage layers.

        Args:
            chat_id: The chat session ID
            mcp_server_name: The MCP server name

        Returns:
            True if deleted
        """
        cache_key = self._cache_key(chat_id, mcp_server_name)

        # Remove from memory
        self._sessions.pop(cache_key, None)

        # Remove from cache
        if self._cache:
            try:
                await self._cache.delete(cache_key)
            except Exception as e:
                logger.warning("Failed to delete from cache", error=str(e))

        # Remove from persistence
        if self._persistence:
            try:
                await self._persistence.delete(cache_key)
            except Exception as e:
                logger.warning("Failed to delete from persistence", error=str(e))

        logger.info("Deleted MCP session", chat_id=chat_id, mcp_server=mcp_server_name)
        return True

    async def list_sessions(
        self,
        chat_id: Optional[str] = None,
    ) -> list[MCPSessionState]:
        """
        List active sessions.

        Args:
            chat_id: Optional filter by chat ID

        Returns:
            List of MCPSessionState objects
        """
        sessions = list(self._sessions.values())

        if chat_id:
            sessions = [s for s in sessions if s.chat_id == chat_id]

        return sessions

    async def close(self) -> None:
        """
        Close the session manager and persist all sessions.
        """
        if self._persistence and self._config.persist_sessions:
            for session in self._sessions.values():
                try:
                    cache_key = self._cache_key(session.chat_id, session.mcp_server_name)
                    await self._persistence.save(cache_key, session.to_dict())
                except Exception as e:
                    logger.warning(
                        "Failed to persist session on close",
                        session_id=session.session_id,
                        error=str(e),
                    )

        self._sessions.clear()
        logger.info("MCPSessionManager closed")


def parse_mcp_session_config(config_dict: Dict[str, Any]) -> MCPSessionConfig:
    """
    Parse MCP session configuration from agent config.

    Expected format:
        [agent.mcp_sessions]
        enabled = true
        session_ttl = 3600
        persist_sessions = true

    Args:
        config_dict: The agent configuration dictionary

    Returns:
        MCPSessionConfig instance
    """
    session_config = config_dict.get("mcp_sessions", {})

    return MCPSessionConfig(
        enabled=session_config.get("enabled", False),
        session_ttl=session_config.get("session_ttl", 3600),
        persist_sessions=session_config.get("persist_sessions", True),
        cache_prefix=session_config.get("cache_prefix", "mcp_session:"),
    )
