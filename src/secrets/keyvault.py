"""
Azure Key Vault Integration for Secrets Management.

Provides secure access to secrets with:
- Environment variable fallback
- Caching to reduce Key Vault calls
- Async support
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger(__name__)

# Global secret manager instance
_secret_manager: Optional["SecretManager"] = None


@dataclass
class SecretConfig:
    """Configuration for secrets management."""
    # Key Vault settings
    keyvault_enabled: bool = False
    keyvault_url: str = ""  # e.g., "https://my-vault.vault.azure.net/"

    # Caching
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300  # 5 minutes

    # Fallback behavior
    allow_env_fallback: bool = True
    allow_config_fallback: bool = False  # Only for development

    # Secret name mapping (Key Vault name -> env var name)
    name_mapping: Dict[str, str] = field(default_factory=dict)


class SecretManager:
    """
    Manages secrets from Azure Key Vault with caching and fallbacks.

    Priority order:
    1. Environment variables (if allow_env_fallback)
    2. Azure Key Vault
    3. Local config (if allow_config_fallback, development only)
    """

    def __init__(self, config: SecretConfig):
        """
        Initialize secret manager.

        Args:
            config: SecretConfig with settings
        """
        self.config = config
        self._kv_client = None
        self._cache: Dict[str, tuple[str, float]] = {}  # name -> (value, expiry_time)
        self._initialized = False

        logger.info(
            "Secret manager initialized",
            keyvault_enabled=config.keyvault_enabled,
            cache_enabled=config.cache_enabled
        )

    async def _ensure_client(self) -> bool:
        """Initialize Key Vault client if needed."""
        if not self.config.keyvault_enabled:
            return False

        if self._initialized:
            return self._kv_client is not None

        self._initialized = True

        if not self.config.keyvault_url:
            logger.warning("Key Vault URL not configured")
            return False

        try:
            from azure.keyvault.secrets.aio import SecretClient
            from azure.identity.aio import DefaultAzureCredential

            credential = DefaultAzureCredential()
            self._kv_client = SecretClient(
                vault_url=self.config.keyvault_url,
                credential=credential
            )

            logger.info("Key Vault client initialized", url=self.config.keyvault_url)
            return True

        except ImportError:
            logger.warning(
                "azure-keyvault-secrets not installed",
                install_hint="pip install azure-keyvault-secrets"
            )
            return False
        except Exception as e:
            logger.error("Failed to initialize Key Vault client", error=str(e))
            return False

    def get_secret_sync(
        self,
        name: str,
        default: Optional[str] = None
    ) -> Optional[str]:
        """
        Get a secret synchronously (env vars and cache only).

        Args:
            name: Secret name
            default: Default value if not found

        Returns:
            Secret value or default
        """
        # Check cache first
        if self.config.cache_enabled and name in self._cache:
            value, expiry = self._cache[name]
            if time.time() < expiry:
                logger.debug("Secret cache hit", name=name)
                return value
            else:
                del self._cache[name]

        # Check environment variable
        if self.config.allow_env_fallback:
            env_name = self.config.name_mapping.get(name, name)
            env_value = os.getenv(env_name) or os.getenv(name.upper().replace("-", "_"))
            if env_value:
                logger.debug("Secret from environment", name=name)
                self._cache_secret(name, env_value)
                return env_value

        return default

    async def get_secret(
        self,
        name: str,
        default: Optional[str] = None
    ) -> Optional[str]:
        """
        Get a secret asynchronously.

        Args:
            name: Secret name
            default: Default value if not found

        Returns:
            Secret value or default
        """
        # Try sync methods first
        sync_value = self.get_secret_sync(name, None)
        if sync_value is not None:
            return sync_value

        # Try Key Vault
        if await self._ensure_client() and self._kv_client:
            try:
                secret = await self._kv_client.get_secret(name)
                value = secret.value
                logger.debug("Secret from Key Vault", name=name)
                self._cache_secret(name, value)
                return value
            except Exception as e:
                logger.warning("Failed to get secret from Key Vault", name=name, error=str(e))

        return default

    def _cache_secret(self, name: str, value: str) -> None:
        """Cache a secret value."""
        if self.config.cache_enabled:
            expiry = time.time() + self.config.cache_ttl_seconds
            self._cache[name] = (value, expiry)

    async def set_secret(
        self,
        name: str,
        value: str
    ) -> bool:
        """
        Set a secret in Key Vault.

        Args:
            name: Secret name
            value: Secret value

        Returns:
            True if successful
        """
        if not await self._ensure_client() or not self._kv_client:
            logger.warning("Cannot set secret: Key Vault not available")
            return False

        try:
            await self._kv_client.set_secret(name, value)
            self._cache_secret(name, value)
            logger.info("Secret set in Key Vault", name=name)
            return True
        except Exception as e:
            logger.error("Failed to set secret", name=name, error=str(e))
            return False

    async def delete_secret(self, name: str) -> bool:
        """
        Delete a secret from Key Vault.

        Args:
            name: Secret name

        Returns:
            True if successful
        """
        if not await self._ensure_client() or not self._kv_client:
            return False

        try:
            poller = await self._kv_client.begin_delete_secret(name)
            await poller.wait()
            self._cache.pop(name, None)
            logger.info("Secret deleted from Key Vault", name=name)
            return True
        except Exception as e:
            logger.error("Failed to delete secret", name=name, error=str(e))
            return False

    async def list_secrets(self) -> list:
        """List all secret names in Key Vault."""
        if not await self._ensure_client() or not self._kv_client:
            return []

        try:
            secrets = []
            async for secret in self._kv_client.list_properties_of_secrets():
                secrets.append(secret.name)
            return secrets
        except Exception as e:
            logger.error("Failed to list secrets", error=str(e))
            return []

    def clear_cache(self) -> None:
        """Clear the secret cache."""
        self._cache.clear()
        logger.debug("Secret cache cleared")

    async def close(self) -> None:
        """Close the Key Vault client."""
        if self._kv_client:
            await self._kv_client.close()
            self._kv_client = None
        self._cache.clear()
        logger.debug("Secret manager closed")


def get_secret_manager(config: SecretConfig = None) -> SecretManager:
    """
    Get or create the global secret manager instance.

    Args:
        config: Optional SecretConfig (only used on first call)

    Returns:
        SecretManager instance
    """
    global _secret_manager

    if _secret_manager is None:
        _secret_manager = SecretManager(config or SecretConfig())

    return _secret_manager


async def get_secret(
    name: str,
    default: Optional[str] = None
) -> Optional[str]:
    """
    Convenience function to get a secret.

    Args:
        name: Secret name
        default: Default value

    Returns:
        Secret value or default
    """
    manager = get_secret_manager()
    return await manager.get_secret(name, default)
