"""
Redis Cache for Chat History.

Uses Azure Cache for Redis with Microsoft Entra ID (AAD) authentication.
No API keys - uses DefaultAzureCredential for secure access.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CacheConfig:
    """Redis cache configuration."""
    enabled: bool = False
    host: str = ""
    port: int = 6380  # Azure Cache for Redis uses SSL on 6380
    ssl: bool = True
    ttl: int = 3600  # 1 hour default
    prefix: str = "chat:"
    database: int = 0


class RedisCache:
    """
    Azure Cache for Redis with AAD authentication.
    
    Uses DefaultAzureCredential for authentication (no API keys).
    Stores serialized chat threads with configurable TTL.
    """
    
    def __init__(self, config: CacheConfig):
        """
        Initialize Redis cache.
        
        Args:
            config: CacheConfig with connection settings
        """
        self.config = config
        self._client = None
        self._credential = None
        self._initialized = False
        
        if not config.enabled:
            logger.info("Redis cache disabled")
            return
            
        if not config.host:
            logger.warning("Redis cache enabled but no host configured")
            self.config.enabled = False
    
    async def _ensure_connected(self) -> bool:
        """Ensure Redis connection is established."""
        if not self.config.enabled:
            return False
            
        if self._initialized:
            return self._client is not None
        
        self._initialized = True
        
        try:
            import redis.asyncio as redis_async
            from azure.identity.aio import DefaultAzureCredential
            import jwt
            
            self._credential = DefaultAzureCredential()
            
            # Get token for Azure Cache for Redis
            token_response = await self._credential.get_token(
                "https://redis.azure.com/.default"
            )
            
            # Extract the OID (Object ID) from the token for username
            # Azure Cache for Redis requires username = OID from the AAD token
            try:
                decoded = jwt.decode(
                    token_response.token, 
                    options={"verify_signature": False}
                )
                username = decoded.get("oid", "")
                logger.debug("Extracted OID from token", oid=username[:8] + "..." if username else "N/A")
            except Exception as e:
                logger.warning("Could not decode token for OID, using empty username", error=str(e))
                username = ""
            
            # Connect with AAD token as password and OID as username
            self._client = redis_async.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.database,
                username=username,  # OID from the AAD token
                password=token_response.token,  # The actual access token
                ssl=self.config.ssl,
                decode_responses=True,
                socket_timeout=10,
                socket_connect_timeout=10,
            )
            
            # Test connection
            await self._client.ping()
            logger.info("Redis cache connected", host=self.config.host)
            return True
            
        except ImportError as e:
            logger.warning("Required package not installed for Redis", error=str(e))
            self.config.enabled = False
            return False
        except Exception as e:
            logger.warning("Redis connection failed, falling back to in-memory", error=str(e))
            self._client = None
            return False
    
    def _make_key(self, chat_id: str) -> str:
        """Create Redis key for chat ID."""
        return f"{self.config.prefix}{chat_id}"
    
    async def get(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Get serialized thread from cache.
        
        Args:
            chat_id: The chat session ID
            
        Returns:
            Serialized thread data or None if not found
        """
        if not await self._ensure_connected():
            return None
        
        try:
            key = self._make_key(chat_id)
            data = await self._client.get(key)
            
            if data:
                logger.debug("Cache hit", chat_id=chat_id)
                return json.loads(data)
            
            logger.debug("Cache miss", chat_id=chat_id)
            return None
            
        except Exception as e:
            logger.warning("Cache get failed", chat_id=chat_id, error=str(e))
            return None
    
    async def set(
        self, 
        chat_id: str, 
        thread_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Store serialized thread in cache.
        
        Args:
            chat_id: The chat session ID
            thread_data: Serialized thread data
            ttl: Optional TTL override in seconds
            
        Returns:
            True if stored successfully
        """
        if not await self._ensure_connected():
            return False
        
        try:
            key = self._make_key(chat_id)
            data = json.dumps(thread_data)
            ttl = ttl or self.config.ttl
            
            await self._client.setex(key, ttl, data)
            logger.debug("Cache set", chat_id=chat_id, ttl=ttl)
            return True
            
        except Exception as e:
            logger.warning("Cache set failed", chat_id=chat_id, error=str(e))
            return False
    
    async def delete(self, chat_id: str) -> bool:
        """Delete chat from cache."""
        if not await self._ensure_connected():
            return False
        
        try:
            key = self._make_key(chat_id)
            await self._client.delete(key)
            logger.debug("Cache delete", chat_id=chat_id)
            return True
        except Exception as e:
            logger.warning("Cache delete failed", chat_id=chat_id, error=str(e))
            return False
    
    async def get_ttl(self, chat_id: str) -> Optional[int]:
        """Get remaining TTL for a chat."""
        if not await self._ensure_connected():
            return None
        
        try:
            key = self._make_key(chat_id)
            ttl = await self._client.ttl(key)
            return ttl if ttl > 0 else None
        except Exception:
            return None
    
    async def list_keys(self, pattern: str = "*") -> List[str]:
        """List all chat IDs matching pattern."""
        if not await self._ensure_connected():
            return []
        
        try:
            full_pattern = f"{self.config.prefix}{pattern}"
            keys = await self._client.keys(full_pattern)
            # Strip prefix to return just chat IDs
            prefix_len = len(self.config.prefix)
            return [k[prefix_len:] for k in keys]
        except Exception as e:
            logger.warning("Cache list failed", error=str(e))
            return []
    
    async def get_metadata(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata about cached thread (without full data)."""
        if not await self._ensure_connected():
            return None
        
        try:
            key = self._make_key(chat_id)
            
            # Get TTL and check existence
            pipe = self._client.pipeline()
            pipe.exists(key)
            pipe.ttl(key)
            results = await pipe.execute()
            
            exists, ttl = results
            if not exists:
                return None
            
            return {
                "chat_id": chat_id,
                "ttl_remaining": ttl if ttl > 0 else None,
                "cached": True
            }
        except Exception:
            return None
    
    async def refresh_ttl(self, chat_id: str, ttl: Optional[int] = None) -> bool:
        """Refresh TTL for a chat without updating data."""
        if not await self._ensure_connected():
            return False
        
        try:
            key = self._make_key(chat_id)
            ttl = ttl or self.config.ttl
            await self._client.expire(key, ttl)
            return True
        except Exception:
            return False
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._credential:
            await self._credential.close()
            self._credential = None
        logger.debug("Redis cache closed")


class InMemoryCache:
    """
    In-memory fallback cache.
    
    Used when Redis is unavailable or disabled.
    Data is lost on application restart.
    """
    
    def __init__(self, ttl: int = 3600):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._timestamps: Dict[str, datetime] = {}
        self.ttl = ttl
    
    async def get(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get thread data from memory."""
        self._cleanup_expired()
        return self._store.get(chat_id)
    
    async def set(
        self, 
        chat_id: str, 
        thread_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Store thread data in memory."""
        self._store[chat_id] = thread_data
        self._timestamps[chat_id] = datetime.now(timezone.utc)
        return True
    
    async def delete(self, chat_id: str) -> bool:
        """Delete from memory."""
        self._store.pop(chat_id, None)
        self._timestamps.pop(chat_id, None)
        return True
    
    async def list_keys(self, pattern: str = "*") -> List[str]:
        """List all chat IDs."""
        self._cleanup_expired()
        return list(self._store.keys())
    
    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        now = datetime.now(timezone.utc)
        expired = [
            k for k, ts in self._timestamps.items()
            if (now - ts).total_seconds() > self.ttl
        ]
        for k in expired:
            self._store.pop(k, None)
            self._timestamps.pop(k, None)
    
    async def close(self) -> None:
        """Clear memory store."""
        self._store.clear()
        self._timestamps.clear()
