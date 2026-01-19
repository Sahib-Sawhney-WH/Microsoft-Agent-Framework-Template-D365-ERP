"""
ADLS Persistence for Chat History.

Uses Azure Data Lake Storage Gen2 for long-term chat history storage.
Authentication via DefaultAzureCredential (no API keys).
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PersistenceConfig:
    """ADLS persistence configuration."""
    enabled: bool = False
    account_name: str = ""
    container: str = "chat-history"
    folder: str = "threads"
    # Schedule: persist X seconds before cache TTL expires
    # Format: "ttl+300" means persist 300s before TTL (5 min buffer)
    schedule: str = "ttl+300"
    

class ADLSPersistence:
    """
    Azure Data Lake Storage Gen2 for chat history persistence.
    
    Uses DefaultAzureCredential - no API keys required.
    Stores serialized chat threads as JSON blobs.
    """
    
    def __init__(self, config: PersistenceConfig):
        """
        Initialize ADLS persistence.
        
        Args:
            config: PersistenceConfig with storage settings
        """
        self.config = config
        self._client = None
        self._container_client = None
        self._initialized = False
        
        if not config.enabled:
            logger.info("ADLS persistence disabled")
            return
            
        if not config.account_name:
            logger.warning("ADLS persistence enabled but no account configured")
            self.config.enabled = False
    
    async def _ensure_connected(self) -> bool:
        """Ensure ADLS connection is established."""
        if not self.config.enabled:
            return False
            
        if self._initialized:
            return self._container_client is not None
        
        self._initialized = True
        
        try:
            # Try blob storage API first (works with any storage account)
            # ADLS Gen2 DFS API requires hierarchical namespace which may not be enabled
            from azure.storage.blob.aio import BlobServiceClient
            from azure.identity.aio import DefaultAzureCredential
            
            credential = DefaultAzureCredential()
            
            # Use blob endpoint instead of DFS
            account_url = f"https://{self.config.account_name}.blob.core.windows.net"
            self._client = BlobServiceClient(
                account_url=account_url,
                credential=credential
            )
            
            self._container_client = self._client.get_container_client(
                self.config.container
            )
            
            # Check if container exists
            try:
                await self._container_client.get_container_properties()
            except Exception:
                logger.info("Creating container", container=self.config.container)
                await self._container_client.create_container()
            
            # Store flag for API type
            self._using_blob_api = True
            
            logger.info(
                "ADLS persistence connected",
                account=self.config.account_name,
                container=self.config.container
            )
            return True
            
        except ImportError:
            logger.warning("azure-storage-blob not installed, persistence disabled")
            self.config.enabled = False
            return False
        except Exception as e:
            logger.warning("ADLS connection failed", error=str(e))
            self._container_client = None
            return False
    
    def _make_path(self, chat_id: str) -> str:
        """Create blob path for chat ID."""
        return f"{self.config.folder}/{chat_id}.json"
    
    async def get(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Load serialized thread from ADLS.
        
        Args:
            chat_id: The chat session ID
            
        Returns:
            Serialized thread data or None if not found
        """
        if not await self._ensure_connected():
            return None
        
        try:
            path = self._make_path(chat_id)
            blob_client = self._container_client.get_blob_client(path)
            
            download = await blob_client.download_blob()
            content = await download.readall()
            data = json.loads(content.decode('utf-8'))
            
            logger.debug("ADLS load success", chat_id=chat_id)
            return data
            
        except Exception as e:
            # File not found is expected for new chats
            if "BlobNotFound" in str(e) or "PathNotFound" in str(e):
                logger.debug("ADLS file not found", chat_id=chat_id)
            else:
                logger.warning("ADLS load failed", chat_id=chat_id, error=str(e))
            return None
    
    async def save(
        self, 
        chat_id: str, 
        thread_data: Dict[str, Any],
        metadata: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        Save serialized thread to ADLS.
        
        Args:
            chat_id: The chat session ID
            thread_data: Serialized thread data
            metadata: Optional metadata to attach to blob
            
        Returns:
            True if saved successfully
        """
        if not await self._ensure_connected():
            return False
        
        try:
            path = self._make_path(chat_id)
            blob_client = self._container_client.get_blob_client(path)
            
            # Add timestamp to data
            thread_data["_persisted_at"] = datetime.now(timezone.utc).isoformat()
            thread_data["_chat_id"] = chat_id
            
            content = json.dumps(thread_data, indent=2, default=str)
            
            # Create/overwrite blob
            await blob_client.upload_blob(
                content.encode('utf-8'),
                overwrite=True,
                metadata=metadata
            )
            
            logger.debug("ADLS save success", chat_id=chat_id)
            return True
            
        except Exception as e:
            logger.error("ADLS save failed", chat_id=chat_id, error=str(e))
            return False
    
    async def delete(self, chat_id: str) -> bool:
        """Delete chat from ADLS."""
        if not await self._ensure_connected():
            return False
        
        try:
            path = self._make_path(chat_id)
            blob_client = self._container_client.get_blob_client(path)
            await blob_client.delete_blob()
            logger.debug("ADLS delete success", chat_id=chat_id)
            return True
        except Exception as e:
            logger.warning("ADLS delete failed", chat_id=chat_id, error=str(e))
            return False
    
    async def exists(self, chat_id: str) -> bool:
        """Check if chat exists in ADLS."""
        if not await self._ensure_connected():
            return False
        
        try:
            path = self._make_path(chat_id)
            blob_client = self._container_client.get_blob_client(path)
            await blob_client.get_blob_properties()
            return True
        except Exception:
            return False
    
    async def list_chats(
        self, 
        prefix: str = "",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List persisted chats with metadata.
        
        Args:
            prefix: Optional prefix filter
            limit: Maximum number of results
            
        Returns:
            List of chat metadata dicts
        """
        if not await self._ensure_connected():
            return []
        
        try:
            folder = self.config.folder
            if prefix:
                folder = f"{folder}/{prefix}"
            
            results = []
            async for path in self._container_client.get_paths(path=folder):
                if path.name.endswith('.json'):
                    # Extract chat_id from path
                    chat_id = path.name.rsplit('/', 1)[-1].replace('.json', '')
                    results.append({
                        "chat_id": chat_id,
                        "path": path.name,
                        "size": path.content_length,
                        "last_modified": path.last_modified,
                        "persisted": True
                    })
                    if len(results) >= limit:
                        break
            
            return results
            
        except Exception as e:
            logger.warning("ADLS list failed", error=str(e))
            return []
    
    async def get_metadata(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a chat without loading full data."""
        if not await self._ensure_connected():
            return None
        
        try:
            path = self._make_path(chat_id)
            file_client = self._container_client.get_file_client(path)
            props = await file_client.get_file_properties()
            
            return {
                "chat_id": chat_id,
                "size": props.size,
                "last_modified": props.last_modified,
                "persisted": True,
                "metadata": props.metadata
            }
        except Exception:
            return None
    
    def parse_schedule(self, cache_ttl: int) -> int:
        """
        Parse persist schedule and return seconds before TTL.
        
        Format: "ttl+SECONDS" means persist SECONDS before cache TTL expires.
        Example: cache_ttl=3600, schedule="ttl+300" -> persist at 3300s (300s before expiry)
        
        Args:
            cache_ttl: The cache TTL in seconds
            
        Returns:
            When to persist (in seconds from cache write)
        """
        schedule = self.config.schedule.strip().lower()
        
        if schedule.startswith("ttl+"):
            try:
                buffer = int(schedule.replace("ttl+", ""))
                return max(0, cache_ttl - buffer)
            except ValueError:
                logger.warning("Invalid persist schedule", schedule=schedule)
                return cache_ttl - 300  # Default 5 min buffer
        
        # Try parsing as absolute seconds
        try:
            return int(schedule)
        except ValueError:
            return cache_ttl - 300
    
    async def close(self) -> None:
        """Close ADLS connection."""
        if self._client:
            await self._client.close()
            self._client = None
            self._container_client = None
        logger.debug("ADLS persistence closed")
