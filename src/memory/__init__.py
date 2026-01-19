"""
Memory module - Chat history caching and persistence.

Provides:
- RedisCache: Azure Cache for Redis with AAD auth
- ADLSPersistence: Azure Data Lake Storage for long-term storage
- ChatHistoryManager: Orchestrates cache + persistence with merge logic
"""

from src.memory.cache import RedisCache
from src.memory.persistence import ADLSPersistence
from src.memory.manager import ChatHistoryManager

__all__ = [
    "RedisCache",
    "ADLSPersistence",
    "ChatHistoryManager",
]
