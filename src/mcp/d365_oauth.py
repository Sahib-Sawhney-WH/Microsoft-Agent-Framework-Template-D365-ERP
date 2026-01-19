"""
D365 F&O OAuth token provider using Azure Identity.

Acquires and caches OAuth tokens for D365 Finance & Operations MCP access.
Supports both DefaultAzureCredential (for flexibility) and ClientSecretCredential
(for service accounts).

Production features:
- Retry logic with exponential backoff for transient failures
- Thread-safe token refresh with async lock
- Pydantic config model support
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Union

import structlog

logger = structlog.get_logger(__name__)

# Azure Identity imports - optional dependency
try:
    from azure.identity.aio import (
        ClientSecretCredential,
        DefaultAzureCredential,
    )
    AZURE_IDENTITY_AVAILABLE = True
except ImportError:
    AZURE_IDENTITY_AVAILABLE = False
    ClientSecretCredential = None
    DefaultAzureCredential = None

# Tenacity for retry logic - optional but recommended
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_sleep_log,
        RetryError,
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    RetryError = Exception

# Config model import
try:
    from src.models.config import D365OAuthConfig
    CONFIG_MODEL_AVAILABLE = True
except ImportError:
    CONFIG_MODEL_AVAILABLE = False
    D365OAuthConfig = None


class D365TokenProvider:
    """
    Acquires OAuth tokens for D365 F&O MCP access.

    Uses Azure Identity for token acquisition - supports:
    - DefaultAzureCredential (recommended for flexibility)
    - ClientSecretCredential (for service accounts)

    The token is cached and automatically refreshed when expired.
    Production features include retry logic and thread-safe refresh.

    Usage:
        # Using config model (recommended)
        from src.models.config import D365OAuthConfig

        config = D365OAuthConfig(
            environment_url="https://myorg.operations.dynamics.com",
            tenant_id="your-tenant-id",
            client_id="your-client-id",
            client_secret="your-secret",
        )
        provider = D365TokenProvider(config=config)

        # Or using direct parameters
        provider = D365TokenProvider(
            environment_url="https://myorg.operations.dynamics.com",
            tenant_id="your-tenant-id",
            client_id="your-client-id",
            client_secret="your-secret",
        )

        token = await provider.get_token()
        # Use token in Authorization header
    """

    def __init__(
        self,
        config: Optional["D365OAuthConfig"] = None,
        *,
        # Direct parameters (used if config not provided)
        environment_url: Optional[str] = None,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        token_refresh_buffer_minutes: int = 5,
    ):
        """
        Initialize the D365 token provider.

        Args:
            config: D365OAuthConfig instance (recommended)
            environment_url: D365 F&O environment URL (e.g., https://myorg.operations.dynamics.com)
            tenant_id: Azure AD tenant ID (optional if using DefaultAzureCredential)
            client_id: App registration client ID (optional if using DefaultAzureCredential)
            client_secret: App registration client secret (optional if using DefaultAzureCredential)
            token_refresh_buffer_minutes: Minutes before expiry to refresh token (default: 5)
        """
        if not AZURE_IDENTITY_AVAILABLE:
            raise ImportError(
                "azure-identity is required for D365 OAuth. "
                "Install with: pip install azure-identity"
            )

        # Use config model if provided, otherwise use direct parameters
        if config is not None:
            self._environment_url = config.environment_url.rstrip("/")
            self._tenant_id = config.tenant_id
            self._client_id = config.client_id
            self._client_secret = config.client_secret
            self._token_refresh_buffer = timedelta(minutes=config.token_refresh_buffer_minutes)
        else:
            if not environment_url:
                raise ValueError("environment_url is required")
            self._environment_url = environment_url.rstrip("/")
            self._tenant_id = tenant_id
            self._client_id = client_id
            self._client_secret = client_secret
            self._token_refresh_buffer = timedelta(minutes=token_refresh_buffer_minutes)

        # D365 F&O uses environment URL as the resource/scope
        self._scope = f"{self._environment_url}/.default"

        self._credential = None
        self._cached_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

        # Thread-safe token refresh lock (Phase 4)
        self._refresh_lock = asyncio.Lock()

        logger.debug(
            "D365TokenProvider initialized",
            environment_url=self._environment_url,
            scope=self._scope,
            use_client_secret=bool(self._client_secret),
        )

    async def get_token(self) -> str:
        """
        Get access token for D365, with thread-safe caching.

        Returns a cached token if still valid, otherwise acquires a new one.
        Uses double-checked locking for thread safety.

        Returns:
            OAuth access token string

        Raises:
            Exception: If token acquisition fails
        """
        # Quick check without lock
        if self._is_token_valid():
            logger.debug("Using cached D365 token")
            return self._cached_token

        # Acquire lock for refresh (Phase 4: thread-safe)
        async with self._refresh_lock:
            # Double-check after acquiring lock
            if self._is_token_valid():
                logger.debug("Token validated after lock acquisition")
                return self._cached_token

            # Acquire new token with retry logic
            return await self._acquire_token_with_retry()

    async def _acquire_token_with_retry(self) -> str:
        """
        Acquire token with retry logic for transient failures.

        Uses tenacity for exponential backoff retries on ConnectionError
        and TimeoutError.

        Returns:
            OAuth access token string
        """
        if self._credential is None:
            self._credential = self._create_credential()

        if TENACITY_AVAILABLE:
            return await self._acquire_token_tenacity()
        else:
            return await self._acquire_token_simple()

    async def _acquire_token_tenacity(self) -> str:
        """Acquire token using tenacity retry decorator."""

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
            before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
            reraise=True,
        )
        async def _acquire():
            token = await self._credential.get_token(self._scope)
            return token

        try:
            token = await _acquire()
            self._cached_token = token.token
            self._token_expires_at = datetime.fromtimestamp(token.expires_on)

            logger.info(
                "Acquired D365 OAuth token",
                scope=self._scope,
                expires_at=self._token_expires_at.isoformat(),
            )
            return self._cached_token

        except RetryError as e:
            logger.error(
                "Failed to acquire D365 token after retries",
                scope=self._scope,
                error=str(e),
            )
            raise
        except Exception as e:
            logger.error(
                "Failed to acquire D365 token",
                scope=self._scope,
                error=str(e),
            )
            raise

    async def _acquire_token_simple(self) -> str:
        """Acquire token with simple manual retry (fallback if tenacity not available)."""
        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                token = await self._credential.get_token(self._scope)
                self._cached_token = token.token
                self._token_expires_at = datetime.fromtimestamp(token.expires_on)

                logger.info(
                    "Acquired D365 OAuth token",
                    scope=self._scope,
                    expires_at=self._token_expires_at.isoformat(),
                )
                return self._cached_token

            except (ConnectionError, TimeoutError, OSError) as e:
                last_error = e
                if attempt < max_attempts - 1:
                    backoff = min(2 ** attempt, 10)
                    logger.warning(
                        "Token acquisition failed, retrying",
                        attempt=attempt + 1,
                        backoff=backoff,
                        error=str(e),
                    )
                    await asyncio.sleep(backoff)
                    continue
                raise
            except Exception as e:
                logger.error(
                    "Failed to acquire D365 token",
                    scope=self._scope,
                    error=str(e),
                )
                raise

        raise last_error or RuntimeError("Token acquisition failed")

    def _create_credential(self):
        """
        Create appropriate Azure credential based on configuration.

        If client_secret, tenant_id, and client_id are all provided,
        uses ClientSecretCredential. Otherwise, uses DefaultAzureCredential.

        Returns:
            Azure credential instance
        """
        if self._client_secret and self._tenant_id and self._client_id:
            logger.debug("Using ClientSecretCredential for D365 auth")
            return ClientSecretCredential(
                tenant_id=self._tenant_id,
                client_id=self._client_id,
                client_secret=self._client_secret,
            )

        logger.debug("Using DefaultAzureCredential for D365 auth")
        return DefaultAzureCredential()

    def _is_token_valid(self) -> bool:
        """
        Check if cached token is valid (with buffer before expiry).

        Returns:
            True if token exists and won't expire within the buffer period
        """
        if not self._cached_token or not self._token_expires_at:
            return False

        # Refresh token before it expires (with buffer)
        expiry_threshold = self._token_expires_at - self._token_refresh_buffer
        return datetime.now() < expiry_threshold

    async def refresh_token(self) -> str:
        """
        Force refresh the OAuth token.

        Clears the cached token and acquires a new one.
        Thread-safe using async lock.

        Returns:
            New OAuth access token string
        """
        async with self._refresh_lock:
            self._cached_token = None
            self._token_expires_at = None
            return await self._acquire_token_with_retry()

    @property
    def environment_url(self) -> str:
        """Get the D365 environment URL."""
        return self._environment_url

    @property
    def scope(self) -> str:
        """Get the OAuth scope."""
        return self._scope

    @property
    def token_expires_at(self) -> Optional[datetime]:
        """Get the token expiration time."""
        return self._token_expires_at

    @property
    def is_token_cached(self) -> bool:
        """Check if a token is currently cached."""
        return self._cached_token is not None

    async def close(self) -> None:
        """
        Close the credential and release resources.

        Should be called when the token provider is no longer needed.
        """
        if self._credential:
            try:
                await self._credential.close()
                logger.debug("D365TokenProvider credential closed")
            except Exception as e:
                logger.warning("Error closing D365 credential", error=str(e))
            finally:
                self._credential = None
                self._cached_token = None
                self._token_expires_at = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False
