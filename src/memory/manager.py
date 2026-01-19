"""
Chat History Manager.

Orchestrates cache (Redis) and persistence (ADLS) with:
- Automatic fallback when cache unavailable
- Merge logic when persisting from cache
- Background persist scheduling
- Context summarization for long conversations
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass, field

import structlog

from src.memory.cache import RedisCache, InMemoryCache, CacheConfig
from src.memory.persistence import ADLSPersistence, PersistenceConfig

if TYPE_CHECKING:
    from agent_framework import ChatAgent

logger = structlog.get_logger(__name__)


# Token estimation constants
AVG_CHARS_PER_TOKEN = 4  # Rough estimate for English text
DEFAULT_MAX_TOKENS = 8000  # Max tokens before summarization
SUMMARY_TARGET_TOKENS = 2000  # Target size for summary
RECENT_MESSAGES_TO_KEEP = 5  # Keep recent messages after summarization


@dataclass
class SummarizationConfig:
    """Configuration for context summarization."""
    enabled: bool = True
    max_tokens: int = DEFAULT_MAX_TOKENS
    summary_target_tokens: int = SUMMARY_TARGET_TOKENS
    recent_messages_to_keep: int = RECENT_MESSAGES_TO_KEEP
    summary_model: Optional[str] = None  # Use default model if None


@dataclass
class MemoryConfig:
    """Complete memory configuration."""
    cache: CacheConfig = field(default_factory=CacheConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    summarization: SummarizationConfig = field(default_factory=SummarizationConfig)


@dataclass
class ChatSession:
    """Represents an active chat session."""
    chat_id: str
    thread: Any  # Agent thread object
    created_at: datetime
    last_accessed: datetime
    message_count: int = 0
    persisted: bool = False
    summarized: bool = False
    summary_count: int = 0  # Number of times this session has been summarized
    estimated_tokens: int = 0
    # MCP session references for stateful MCP servers
    mcp_sessions: Dict[str, str] = field(default_factory=dict)  # server_name -> session_id
    

class ChatHistoryManager:
    """
    Orchestrates chat history across cache and persistence layers.
    
    Handles all edge cases:
    - chat_id provided, found in cache -> use cached
    - chat_id provided, not in cache, found in ADLS -> load to cache
    - chat_id provided, not found anywhere -> create new with that ID
    - chat_id not provided -> create new with generated UUID
    
    Merge logic for persistence:
    - When persisting, load existing ADLS data
    - Merge new messages from cache (dedupe by timestamp)
    - Save merged result back to ADLS
    """
    
    def __init__(
        self, 
        config: MemoryConfig,
        agent: Optional["ChatAgent"] = None
    ):
        """
        Initialize chat history manager.
        
        Args:
            config: MemoryConfig with cache and persistence settings
            agent: Optional ChatAgent for thread operations
        """
        self.config = config
        self._agent = agent
        
        # Initialize cache (Redis or fallback to in-memory)
        if config.cache.enabled:
            self._cache = RedisCache(config.cache)
        else:
            self._cache = InMemoryCache(ttl=config.cache.ttl)
        
        # Initialize persistence
        self._persistence = ADLSPersistence(config.persistence)
        
        # Track active sessions
        self._sessions: Dict[str, ChatSession] = {}

        # Lock for thread-safe session creation (prevents TOCTOU race condition)
        self._session_lock = asyncio.Lock()

        # Background persist task
        self._persist_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            "ChatHistoryManager initialized",
            cache_enabled=config.cache.enabled,
            persistence_enabled=config.persistence.enabled
        )
    
    def set_agent(self, agent: "ChatAgent") -> None:
        """Set the agent for thread operations."""
        self._agent = agent
    
    async def get_or_create_thread(
        self,
        chat_id: Optional[str] = None
    ) -> tuple[str, Any]:
        """
        Get existing thread or create new one.

        Args:
            chat_id: Optional chat session ID. If not provided, generates new UUID.

        Returns:
            Tuple of (chat_id, thread object)

        Edge cases handled:
        - chat_id=None -> new UUID, new thread
        - chat_id provided, in cache -> deserialize cached thread
        - chat_id provided, not in cache, in ADLS -> load from ADLS, cache it
        - chat_id provided, not found -> new thread with provided ID

        Thread Safety:
        - Uses asyncio.Lock to prevent TOCTOU race condition where concurrent
          requests with the same chat_id could create duplicate sessions.
        """
        if self._agent is None:
            raise RuntimeError("Agent not set. Call set_agent() first.")

        # Use lock to prevent race conditions in concurrent session creation
        async with self._session_lock:
            # Generate ID if not provided
            if not chat_id:
                chat_id = str(uuid.uuid4())
                logger.info("Generated new chat_id", chat_id=chat_id)
                return await self._create_new_session(chat_id)

            # Check if session already exists (double-check under lock)
            if chat_id in self._sessions:
                session = self._sessions[chat_id]
                session.last_accessed = datetime.now(timezone.utc)
                logger.debug("Returning existing session from memory", chat_id=chat_id)
                return chat_id, session.thread

            # Try cache first
            cached = await self._cache.get(chat_id)
            if cached:
                logger.info("Loading thread from cache", chat_id=chat_id)
                return await self._restore_session(chat_id, cached)

            # Try ADLS if persistence enabled
            if self.config.persistence.enabled:
                persisted = await self._persistence.get(chat_id)
                if persisted:
                    logger.info("Loading thread from ADLS", chat_id=chat_id)
                    # Cache the restored thread
                    await self._cache.set(chat_id, persisted)
                    return await self._restore_session(chat_id, persisted)

            # Not found anywhere - create new with provided ID
            logger.info("Creating new thread with provided chat_id", chat_id=chat_id)
            return await self._create_new_session(chat_id)
    
    async def _create_new_session(self, chat_id: str) -> tuple[str, Any]:
        """Create a new chat session."""
        thread = self._agent.get_new_thread()
        
        session = ChatSession(
            chat_id=chat_id,
            thread=thread,
            created_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc)
        )
        self._sessions[chat_id] = session
        
        return chat_id, thread
    
    def _validate_thread_data(self, thread_data: Dict[str, Any]) -> bool:
        """
        Validate thread data schema before deserialization.

        This prevents insecure deserialization attacks by ensuring the data
        conforms to expected structure before processing.

        Args:
            thread_data: The thread data dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(thread_data, dict):
            logger.warning("Thread data is not a dictionary", data_type=type(thread_data).__name__)
            return False

        # Validate messages structure if present
        if "messages" in thread_data:
            messages = thread_data["messages"]
            if not isinstance(messages, list):
                logger.warning("Thread messages is not a list")
                return False

            for i, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    logger.warning("Message is not a dictionary", index=i)
                    return False

                # Validate required message fields
                if "role" in msg and msg["role"] not in ["system", "user", "assistant", "tool", "function"]:
                    logger.warning("Invalid message role", index=i, role=msg.get("role"))
                    return False

                # Validate content field type
                if "content" in msg:
                    content = msg["content"]
                    if not isinstance(content, (str, list, type(None))):
                        logger.warning("Invalid content type", index=i, content_type=type(content).__name__)
                        return False

        # Validate metadata fields (should be strings or primitives)
        metadata_fields = ["_created_at", "_updated_at", "_persisted_at"]
        for field in metadata_fields:
            if field in thread_data:
                value = thread_data[field]
                if value is not None and not isinstance(value, str):
                    logger.warning("Invalid metadata field type", field=field)
                    return False

        return True

    async def _restore_session(
        self,
        chat_id: str,
        thread_data: Dict[str, Any]
    ) -> tuple[str, Any]:
        """Restore a session from serialized data with schema validation."""
        try:
            # Schema validation to prevent insecure deserialization
            if not self._validate_thread_data(thread_data):
                logger.error(
                    "Thread data failed schema validation, creating new session",
                    chat_id=chat_id
                )
                return await self._create_new_session(chat_id)

            # Make a copy and strip metadata fields before deserializing
            # The framework's deserialize_thread() doesn't expect our metadata fields
            clean_data = dict(thread_data)
            keys_to_strip = [k for k in clean_data.keys() if k.startswith('_')]
            for key in keys_to_strip:
                del clean_data[key]

            logger.debug("Deserializing thread", chat_id=chat_id, keys=list(clean_data.keys()))
            thread = await self._agent.deserialize_thread(clean_data)

            session = ChatSession(
                chat_id=chat_id,
                thread=thread,
                created_at=datetime.fromisoformat(
                    thread_data.get("_created_at", datetime.now(timezone.utc).isoformat())
                ),
                last_accessed=datetime.now(timezone.utc),
                message_count=thread_data.get("_message_count", 0),
                persisted=thread_data.get("_persisted", False)
            )
            self._sessions[chat_id] = session

            return chat_id, thread

        except Exception as e:
            logger.warning(
                "Failed to deserialize thread, creating new",
                chat_id=chat_id,
                error=str(e)
            )
            return await self._create_new_session(chat_id)
    
    async def save_thread(
        self, 
        chat_id: str,
        thread: Any,
        force_persist: bool = False
    ) -> bool:
        """
        Save thread state to cache (and optionally ADLS).
        
        Args:
            chat_id: The chat session ID
            thread: The thread object to serialize
            force_persist: If True, immediately persist to ADLS
            
        Returns:
            True if saved successfully
        """
        try:
            # Serialize thread
            thread_data = await thread.serialize()
            
            # Add metadata
            session = self._sessions.get(chat_id)
            if session:
                session.last_accessed = datetime.now(timezone.utc)
                session.message_count += 1
                thread_data["_created_at"] = session.created_at.isoformat()
                thread_data["_message_count"] = session.message_count
            
            thread_data["_updated_at"] = datetime.now(timezone.utc).isoformat()
            
            # Save to cache
            cached = await self._cache.set(chat_id, thread_data)
            
            # Persist if forced or no cache available
            if force_persist or not cached:
                if self.config.persistence.enabled:
                    await self._persist_with_merge(chat_id, thread_data)
            
            return True
            
        except Exception as e:
            logger.error("Failed to save thread", chat_id=chat_id, error=str(e))
            return False
    
    async def _persist_with_merge(
        self, 
        chat_id: str, 
        new_data: Dict[str, Any]
    ) -> bool:
        """
        Persist to ADLS with merge logic.
        
        If data already exists in ADLS:
        1. Load existing data
        2. Merge messages (new data takes precedence for same timestamps)
        3. Save merged result
        """
        try:
            # Check for existing persisted data
            existing = await self._persistence.get(chat_id)
            
            if existing:
                # Merge: new data takes precedence
                merged = await self._merge_thread_data(existing, new_data)
                merged["_merge_count"] = existing.get("_merge_count", 0) + 1
            else:
                merged = new_data
            
            merged["_persisted"] = True
            merged["_persisted_at"] = datetime.now(timezone.utc).isoformat()
            
            success = await self._persistence.save(chat_id, merged)
            
            if success and chat_id in self._sessions:
                self._sessions[chat_id].persisted = True
            
            return success
            
        except Exception as e:
            logger.error("Persist with merge failed", chat_id=chat_id, error=str(e))
            return False
    
    async def _merge_thread_data(
        self, 
        existing: Dict[str, Any], 
        new: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge two thread data dictionaries.
        
        Strategy:
        - Messages: Combine and dedupe by content hash or timestamp
        - Metadata: New values override existing
        - Preserve oldest created_at, newest updated_at
        """
        merged = {**existing, **new}
        
        # Preserve original creation time
        if "_created_at" in existing:
            merged["_created_at"] = existing["_created_at"]
        
        # If both have messages lists, merge them
        if "messages" in existing and "messages" in new:
            existing_msgs = existing.get("messages", [])
            new_msgs = new.get("messages", [])
            
            # Simple merge: use new messages but don't lose any
            # The framework thread serialization should handle this internally
            # We just ensure we don't truncate
            if len(new_msgs) >= len(existing_msgs):
                merged["messages"] = new_msgs
            else:
                # This shouldn't happen, but preserve all messages
                seen = set()
                all_msgs = []
                for msg in existing_msgs + new_msgs:
                    # Dedupe by content if possible
                    key = str(msg.get("content", "")) + str(msg.get("timestamp", ""))
                    if key not in seen:
                        seen.add(key)
                        all_msgs.append(msg)
                merged["messages"] = all_msgs
        
        logger.debug(
            "Merged thread data",
            existing_msgs=len(existing.get("messages", [])),
            new_msgs=len(new.get("messages", [])),
            merged_msgs=len(merged.get("messages", []))
        )
        
        return merged
    
    async def delete_chat(self, chat_id: str) -> bool:
        """Delete chat from all storage layers."""
        success = True
        
        # Remove from cache
        await self._cache.delete(chat_id)
        
        # Remove from persistence
        if self.config.persistence.enabled:
            if not await self._persistence.delete(chat_id):
                success = False
        
        # Remove from active sessions
        self._sessions.pop(chat_id, None)
        
        return success
    
    async def list_chats(
        self, 
        source: str = "all",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List available chats.
        
        Args:
            source: "cache", "persistence", or "all"
            limit: Maximum number of results
            
        Returns:
            List of chat metadata dicts
        """
        results = []
        seen = set()
        
        # Active sessions
        for chat_id, session in self._sessions.items():
            if len(results) >= limit:
                break
            results.append({
                "chat_id": chat_id,
                "active": True,
                "created_at": session.created_at.isoformat(),
                "last_accessed": session.last_accessed.isoformat(),
                "message_count": session.message_count,
                "persisted": session.persisted
            })
            seen.add(chat_id)
        
        # Cache (if Redis)
        if source in ("cache", "all") and isinstance(self._cache, RedisCache):
            cached_ids = await self._cache.list_keys()
            for chat_id in cached_ids:
                if chat_id not in seen and len(results) < limit:
                    meta = await self._cache.get_metadata(chat_id)
                    if meta:
                        results.append(meta)
                        seen.add(chat_id)
        
        # Persistence
        if source in ("persistence", "all") and self.config.persistence.enabled:
            persisted = await self._persistence.list_chats(limit=limit)
            for item in persisted:
                if item["chat_id"] not in seen and len(results) < limit:
                    results.append(item)
                    seen.add(item["chat_id"])
        
        return results
    
    async def start_background_persist(self) -> None:
        """Start background task to persist chats before cache expiry."""
        if not self.config.persistence.enabled:
            return
        
        if self._running:
            return
        
        self._running = True
        self._persist_task = asyncio.create_task(self._background_persist_loop())
        logger.info("Started background persist task")
    
    async def _background_persist_loop(self) -> None:
        """Background loop to persist chats approaching TTL."""
        cache_ttl = self.config.cache.ttl
        persist_at = self._persistence.parse_schedule(cache_ttl)
        check_interval = min(60, persist_at // 4)  # Check frequently
        
        while self._running:
            try:
                await asyncio.sleep(check_interval)
                
                if not isinstance(self._cache, RedisCache):
                    continue
                
                # Check each cached chat's TTL
                chat_ids = await self._cache.list_keys()
                for chat_id in chat_ids:
                    ttl = await self._cache.get_ttl(chat_id)
                    if ttl is not None and ttl <= (cache_ttl - persist_at):
                        # Time to persist
                        logger.info("Auto-persisting before TTL expiry", chat_id=chat_id, ttl=ttl)
                        cached = await self._cache.get(chat_id)
                        if cached:
                            await self._persist_with_merge(chat_id, cached)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Background persist error", error=str(e))
    
    async def close(self) -> None:
        """Close all connections and stop background tasks."""
        # Stop background task
        self._running = False
        if self._persist_task:
            self._persist_task.cancel()
            try:
                await self._persist_task
            except asyncio.CancelledError:
                pass
        
        # Persist all active sessions before closing
        if self.config.persistence.enabled:
            for chat_id, session in self._sessions.items():
                if not session.persisted:
                    try:
                        thread_data = await session.thread.serialize()
                        await self._persist_with_merge(chat_id, thread_data)
                    except Exception as e:
                        logger.warning("Failed to persist on close", chat_id=chat_id, error=str(e))
        
        # Close connections
        await self._cache.close()
        await self._persistence.close()
        
        self._sessions.clear()
        logger.info("ChatHistoryManager closed")

    # ==================== Summarization Methods ====================

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in a text string.

        Uses a simple character-based estimation. For more accurate
        estimates, consider using tiktoken library.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated token count
        """
        return len(text) // AVG_CHARS_PER_TOKEN

    def estimate_thread_tokens(self, thread: Any) -> int:
        """
        Estimate total tokens in a thread.

        Args:
            thread: The thread object

        Returns:
            Estimated total token count
        """
        try:
            # Try to get messages from thread
            if hasattr(thread, 'messages'):
                messages = thread.messages
            elif hasattr(thread, '_messages'):
                messages = thread._messages
            else:
                # Try serializing to get messages
                return 0

            total_chars = 0
            for msg in messages:
                if hasattr(msg, 'content'):
                    content = msg.content
                elif isinstance(msg, dict):
                    content = msg.get('content', '')
                else:
                    content = str(msg)

                if isinstance(content, str):
                    total_chars += len(content)
                elif isinstance(content, list):
                    # Handle content blocks (text, images, etc.)
                    for block in content:
                        if isinstance(block, dict) and 'text' in block:
                            total_chars += len(block['text'])
                        elif isinstance(block, str):
                            total_chars += len(block)

            return total_chars // AVG_CHARS_PER_TOKEN

        except Exception as e:
            logger.warning("Failed to estimate thread tokens", error=str(e))
            return 0

    async def needs_summarization(self, chat_id: str) -> bool:
        """
        Check if a chat session needs summarization.

        Args:
            chat_id: The chat session ID

        Returns:
            True if summarization is needed
        """
        if not self.config.summarization.enabled:
            return False

        session = self._sessions.get(chat_id)
        if not session:
            return False

        # Estimate current token count
        estimated_tokens = self.estimate_thread_tokens(session.thread)
        session.estimated_tokens = estimated_tokens

        return estimated_tokens > self.config.summarization.max_tokens

    async def summarize_if_needed(
        self,
        chat_id: str,
        summarizer_agent: Optional["ChatAgent"] = None
    ) -> bool:
        """
        Summarize the conversation if it exceeds token limits.

        This method:
        1. Checks if summarization is needed
        2. Extracts messages to summarize
        3. Generates a summary using an LLM
        4. Replaces old messages with summary + recent messages

        Args:
            chat_id: The chat session ID
            summarizer_agent: Optional agent to use for summarization.
                            If not provided, uses the main agent.

        Returns:
            True if summarization was performed
        """
        if not await self.needs_summarization(chat_id):
            return False

        session = self._sessions.get(chat_id)
        if not session:
            return False

        agent = summarizer_agent or self._agent
        if not agent:
            logger.warning("No agent available for summarization")
            return False

        try:
            logger.info(
                "Starting conversation summarization",
                chat_id=chat_id,
                estimated_tokens=session.estimated_tokens
            )

            # Get thread messages
            thread_data = await session.thread.serialize()
            messages = thread_data.get('messages', [])

            if len(messages) <= self.config.summarization.recent_messages_to_keep:
                logger.debug("Not enough messages to summarize", count=len(messages))
                return False

            # Split messages: old (to summarize) and recent (to keep)
            keep_count = self.config.summarization.recent_messages_to_keep
            old_messages = messages[:-keep_count] if keep_count > 0 else messages
            recent_messages = messages[-keep_count:] if keep_count > 0 else []

            # Generate summary
            summary = await self._generate_summary(agent, old_messages)

            if not summary:
                logger.warning("Failed to generate summary")
                return False

            # Create new thread with summary + recent messages
            new_thread = await self._create_summarized_thread(
                session,
                summary,
                recent_messages
            )

            if new_thread:
                # Update session
                old_thread = session.thread
                session.thread = new_thread
                session.summarized = True
                session.summary_count += 1

                # Save to cache
                await self.save_thread(chat_id, new_thread)

                # Estimate new token count
                new_tokens = self.estimate_thread_tokens(new_thread)

                logger.info(
                    "Conversation summarized successfully",
                    chat_id=chat_id,
                    old_message_count=len(messages),
                    new_message_count=len(recent_messages) + 1,
                    old_tokens=session.estimated_tokens,
                    new_tokens=new_tokens,
                    summary_count=session.summary_count
                )

                session.estimated_tokens = new_tokens
                return True

            return False

        except Exception as e:
            logger.error(
                "Summarization failed",
                chat_id=chat_id,
                error=str(e),
                exc_info=True
            )
            return False

    async def _generate_summary(
        self,
        agent: "ChatAgent",
        messages: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Generate a summary of conversation messages.

        Args:
            agent: The agent to use for summarization
            messages: List of messages to summarize

        Returns:
            Summary text or None if failed
        """
        # Format messages for summarization
        conversation_text = self._format_messages_for_summary(messages)

        # Create summarization prompt
        summary_prompt = f"""Please provide a concise summary of the following conversation.
Focus on:
1. Key topics discussed
2. Important decisions or conclusions
3. Any action items or pending questions
4. Context that would be needed to continue the conversation

Keep the summary under {self.config.summarization.summary_target_tokens} tokens.

CONVERSATION:
{conversation_text}

SUMMARY:"""

        try:
            # Use a new thread for summarization to avoid polluting the main thread
            summary_thread = agent.get_new_thread()
            result = await agent.run(summary_prompt, thread=summary_thread)

            if result and hasattr(result, 'text'):
                return result.text
            elif result and hasattr(result, 'content'):
                return result.content
            elif isinstance(result, str):
                return result

            return None

        except Exception as e:
            logger.error("Summary generation failed", error=str(e))
            return None

    def _format_messages_for_summary(
        self,
        messages: List[Dict[str, Any]]
    ) -> str:
        """
        Format messages into readable text for summarization.

        Args:
            messages: List of message dictionaries

        Returns:
            Formatted conversation text
        """
        lines = []

        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')

            # Handle content blocks
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and 'text' in block:
                        text_parts.append(block['text'])
                    elif isinstance(block, str):
                        text_parts.append(block)
                content = ' '.join(text_parts)

            # Truncate very long messages
            if len(content) > 1000:
                content = content[:1000] + '...[truncated]'

            role_label = role.upper()
            lines.append(f"{role_label}: {content}")

        return '\n\n'.join(lines)

    async def _create_summarized_thread(
        self,
        session: ChatSession,
        summary: str,
        recent_messages: List[Dict[str, Any]]
    ) -> Optional[Any]:
        """
        Create a new thread with the summary and recent messages.

        Args:
            session: The current chat session
            summary: The generated summary
            recent_messages: Recent messages to preserve

        Returns:
            New thread object or None if failed
        """
        try:
            # Create new thread
            new_thread = self._agent.get_new_thread()

            # Create the summary message as a system context
            summary_message = {
                "role": "system",
                "content": f"[CONVERSATION SUMMARY]\n{summary}\n[END SUMMARY]\n\nThe conversation continues below:"
            }

            # Construct new thread data
            new_thread_data = {
                "messages": [summary_message] + recent_messages,
                "_summarized": True,
                "_summary_timestamp": datetime.now(timezone.utc).isoformat(),
                "_original_message_count": session.message_count,
                "_created_at": session.created_at.isoformat()
            }

            # Try to deserialize into a proper thread
            # If the framework supports it, use deserialize_thread
            if hasattr(self._agent, 'deserialize_thread'):
                try:
                    # Clean the data before deserialization
                    clean_data = {k: v for k, v in new_thread_data.items() if not k.startswith('_')}
                    return await self._agent.deserialize_thread(clean_data)
                except Exception as e:
                    logger.debug("Could not deserialize summarized thread", error=str(e))

            # Fallback: manually add messages to new thread
            # This depends on the framework's thread implementation
            return new_thread

        except Exception as e:
            logger.error("Failed to create summarized thread", error=str(e))
            return None

    async def get_session_stats(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a chat session.

        Args:
            chat_id: The chat session ID

        Returns:
            Dict with session statistics or None if not found
        """
        session = self._sessions.get(chat_id)
        if not session:
            return None

        # Update token estimate
        session.estimated_tokens = self.estimate_thread_tokens(session.thread)

        return {
            "chat_id": chat_id,
            "created_at": session.created_at.isoformat(),
            "last_accessed": session.last_accessed.isoformat(),
            "message_count": session.message_count,
            "estimated_tokens": session.estimated_tokens,
            "max_tokens": self.config.summarization.max_tokens,
            "needs_summarization": session.estimated_tokens > self.config.summarization.max_tokens,
            "summarized": session.summarized,
            "summary_count": session.summary_count,
            "persisted": session.persisted
        }


def parse_memory_config(config_dict: Dict[str, Any]) -> MemoryConfig:
    """
    Parse memory configuration from TOML config dict.
    
    Expected format:
    [agent.memory]
    enabled = true
    
    [agent.memory.cache]
    enabled = true
    host = "your-redis.redis.cache.windows.net"
    port = 6380
    ssl = true
    ttl = 3600
    prefix = "chat:"
    
    [agent.memory.persistence]
    enabled = true
    account_name = "yourstorageaccount"
    container = "chat-history"
    folder = "threads"
    schedule = "ttl+300"

    [agent.memory.summarization]
    enabled = true
    max_tokens = 8000
    summary_target_tokens = 2000
    recent_messages_to_keep = 5
    """
    memory_dict = config_dict.get("memory", {})

    # Cache config
    cache_dict = memory_dict.get("cache", {})
    cache_config = CacheConfig(
        enabled=cache_dict.get("enabled", False),
        host=cache_dict.get("host", ""),
        port=cache_dict.get("port", 6380),
        ssl=cache_dict.get("ssl", True),
        ttl=cache_dict.get("ttl", 3600),
        prefix=cache_dict.get("prefix", "chat:"),
        database=cache_dict.get("database", 0)
    )

    # Persistence config
    persist_dict = memory_dict.get("persistence", {})
    persist_config = PersistenceConfig(
        enabled=persist_dict.get("enabled", False),
        account_name=persist_dict.get("account_name", ""),
        container=persist_dict.get("container", "chat-history"),
        folder=persist_dict.get("folder", "threads"),
        schedule=persist_dict.get("schedule", "ttl+300")
    )

    # Summarization config
    summary_dict = memory_dict.get("summarization", {})
    summary_config = SummarizationConfig(
        enabled=summary_dict.get("enabled", True),
        max_tokens=summary_dict.get("max_tokens", DEFAULT_MAX_TOKENS),
        summary_target_tokens=summary_dict.get("summary_target_tokens", SUMMARY_TARGET_TOKENS),
        recent_messages_to_keep=summary_dict.get("recent_messages_to_keep", RECENT_MESSAGES_TO_KEEP),
        summary_model=summary_dict.get("summary_model")
    )

    return MemoryConfig(
        cache=cache_config,
        persistence=persist_config,
        summarization=summary_config
    )
