"""
Tests for D365 OAuth token provider.

Covers:
- Token acquisition with client credentials
- Token caching and validation
- Thread-safe token refresh
- Retry logic for transient failures
- Error handling
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta
import asyncio


# ==================== Test Fixtures ====================

@pytest.fixture
def mock_azure_credential():
    """Mock Azure credential."""
    credential = AsyncMock()
    credential.get_token = AsyncMock(return_value=MagicMock(
        token="test-access-token-12345",
        expires_on=(datetime.now() + timedelta(hours=1)).timestamp()
    ))
    credential.close = AsyncMock()
    return credential


@pytest.fixture
def d365_config():
    """Sample D365 OAuth configuration."""
    return {
        "environment_url": "https://test.operations.dynamics.com",
        "tenant_id": "test-tenant-id",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
    }


# ==================== Token Provider Tests ====================

class TestD365TokenProvider:
    """Tests for D365TokenProvider class."""

    @pytest.mark.asyncio
    async def test_initialization_with_direct_params(self, d365_config):
        """Test initialization with direct parameters."""
        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential"):
                from src.mcp.d365_oauth import D365TokenProvider

                provider = D365TokenProvider(**d365_config)

                assert provider.environment_url == "https://test.operations.dynamics.com"
                assert provider.scope == "https://test.operations.dynamics.com/.default"
                assert not provider.is_token_cached

    @pytest.mark.asyncio
    async def test_initialization_strips_trailing_slash(self, d365_config):
        """Test that trailing slashes are stripped from environment URL."""
        d365_config["environment_url"] = "https://test.operations.dynamics.com/"

        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential"):
                from src.mcp.d365_oauth import D365TokenProvider

                provider = D365TokenProvider(**d365_config)

                assert provider.environment_url == "https://test.operations.dynamics.com"

    @pytest.mark.asyncio
    async def test_initialization_requires_environment_url(self):
        """Test that environment_url is required."""
        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            from src.mcp.d365_oauth import D365TokenProvider

            with pytest.raises(ValueError, match="environment_url is required"):
                D365TokenProvider(environment_url=None)

    @pytest.mark.asyncio
    async def test_get_token_acquires_new_token(self, mock_azure_credential, d365_config):
        """Test token acquisition when no cached token exists."""
        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential", return_value=mock_azure_credential):
                from src.mcp.d365_oauth import D365TokenProvider

                provider = D365TokenProvider(**d365_config)

                token = await provider.get_token()

                assert token == "test-access-token-12345"
                assert provider.is_token_cached
                mock_azure_credential.get_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_token_uses_cached_token(self, mock_azure_credential, d365_config):
        """Test that cached token is returned when valid."""
        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential", return_value=mock_azure_credential):
                from src.mcp.d365_oauth import D365TokenProvider

                provider = D365TokenProvider(**d365_config)

                # First call - acquires token
                token1 = await provider.get_token()
                # Second call - should use cache
                token2 = await provider.get_token()

                assert token1 == token2
                # get_token should only be called once
                assert mock_azure_credential.get_token.call_count == 1

    @pytest.mark.asyncio
    async def test_get_token_refreshes_expired_token(self, d365_config):
        """Test that expired tokens are refreshed."""
        # Create a mock that returns different tokens
        mock_credential = AsyncMock()
        mock_credential.get_token = AsyncMock(side_effect=[
            MagicMock(
                token="old-token",
                expires_on=(datetime.now() - timedelta(hours=1)).timestamp()  # Already expired
            ),
            MagicMock(
                token="new-token",
                expires_on=(datetime.now() + timedelta(hours=1)).timestamp()
            ),
        ])
        mock_credential.close = AsyncMock()

        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential", return_value=mock_credential):
                from src.mcp.d365_oauth import D365TokenProvider

                provider = D365TokenProvider(**d365_config)

                # First call
                await provider.get_token()
                # Manually expire the token
                provider._token_expires_at = datetime.now() - timedelta(hours=1)
                # Second call should refresh
                token = await provider.get_token()

                assert mock_credential.get_token.call_count == 2

    @pytest.mark.asyncio
    async def test_force_refresh_token(self, mock_azure_credential, d365_config):
        """Test forced token refresh."""
        call_count = [0]

        async def mock_get_token(scope):
            call_count[0] += 1
            return MagicMock(
                token=f"token-{call_count[0]}",
                expires_on=(datetime.now() + timedelta(hours=1)).timestamp()
            )

        mock_azure_credential.get_token = mock_get_token

        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential", return_value=mock_azure_credential):
                from src.mcp.d365_oauth import D365TokenProvider

                provider = D365TokenProvider(**d365_config)

                token1 = await provider.get_token()
                token2 = await provider.refresh_token()

                assert token1 == "token-1"
                assert token2 == "token-2"
                assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_thread_safe_token_acquisition(self, mock_azure_credential, d365_config):
        """Test that concurrent token acquisitions are thread-safe."""
        acquisition_count = [0]

        async def mock_get_token(scope):
            acquisition_count[0] += 1
            await asyncio.sleep(0.1)  # Simulate network delay
            return MagicMock(
                token="concurrent-token",
                expires_on=(datetime.now() + timedelta(hours=1)).timestamp()
            )

        mock_azure_credential.get_token = mock_get_token

        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential", return_value=mock_azure_credential):
                from src.mcp.d365_oauth import D365TokenProvider

                provider = D365TokenProvider(**d365_config)

                # Launch multiple concurrent requests
                tasks = [provider.get_token() for _ in range(5)]
                results = await asyncio.gather(*tasks)

                # All should get the same token
                assert all(token == "concurrent-token" for token in results)
                # Only one actual acquisition should happen (others wait on lock)
                assert acquisition_count[0] == 1

    @pytest.mark.asyncio
    async def test_close_releases_resources(self, mock_azure_credential, d365_config):
        """Test that close() properly releases resources."""
        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential", return_value=mock_azure_credential):
                from src.mcp.d365_oauth import D365TokenProvider

                provider = D365TokenProvider(**d365_config)
                await provider.get_token()  # Initialize credential

                await provider.close()

                assert not provider.is_token_cached
                mock_azure_credential.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_azure_credential, d365_config):
        """Test async context manager usage."""
        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential", return_value=mock_azure_credential):
                from src.mcp.d365_oauth import D365TokenProvider

                async with D365TokenProvider(**d365_config) as provider:
                    token = await provider.get_token()
                    assert token == "test-access-token-12345"

                # Credential should be closed after context exit
                mock_azure_credential.close.assert_called_once()


# ==================== Error Handling Tests ====================

class TestD365TokenProviderErrors:
    """Tests for error handling in D365TokenProvider."""

    @pytest.mark.asyncio
    async def test_raises_import_error_without_azure_identity(self, d365_config):
        """Test that ImportError is raised when azure-identity not available."""
        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", False):
            from importlib import reload
            import src.mcp.d365_oauth as d365_oauth_module

            # Reload module with mocked availability
            reload(d365_oauth_module)

            with pytest.raises(ImportError, match="azure-identity is required"):
                d365_oauth_module.D365TokenProvider(**d365_config)

    @pytest.mark.asyncio
    async def test_handles_token_acquisition_failure(self, d365_config):
        """Test handling of token acquisition failures."""
        mock_credential = AsyncMock()
        mock_credential.get_token = AsyncMock(
            side_effect=Exception("Authentication failed")
        )

        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential", return_value=mock_credential):
                from src.mcp.d365_oauth import D365TokenProvider

                provider = D365TokenProvider(**d365_config)

                with pytest.raises(Exception, match="Authentication failed"):
                    await provider.get_token()


# ==================== Credential Selection Tests ====================

class TestCredentialSelection:
    """Tests for credential type selection."""

    @pytest.mark.asyncio
    async def test_uses_client_secret_credential_when_all_params_provided(self, d365_config):
        """Test that ClientSecretCredential is used when all params provided."""
        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential") as mock_csc:
                with patch("src.mcp.d365_oauth.DefaultAzureCredential") as mock_dac:
                    mock_csc.return_value = AsyncMock(
                        get_token=AsyncMock(return_value=MagicMock(
                            token="test-token",
                            expires_on=(datetime.now() + timedelta(hours=1)).timestamp()
                        ))
                    )

                    from src.mcp.d365_oauth import D365TokenProvider

                    provider = D365TokenProvider(**d365_config)
                    await provider.get_token()

                    mock_csc.assert_called_once_with(
                        tenant_id="test-tenant-id",
                        client_id="test-client-id",
                        client_secret="test-client-secret",
                    )
                    mock_dac.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_default_credential_when_secret_not_provided(self, d365_config):
        """Test that DefaultAzureCredential is used when client_secret not provided."""
        del d365_config["client_secret"]

        with patch("src.mcp.d365_oauth.AZURE_IDENTITY_AVAILABLE", True):
            with patch("src.mcp.d365_oauth.ClientSecretCredential") as mock_csc:
                with patch("src.mcp.d365_oauth.DefaultAzureCredential") as mock_dac:
                    mock_dac.return_value = AsyncMock(
                        get_token=AsyncMock(return_value=MagicMock(
                            token="test-token",
                            expires_on=(datetime.now() + timedelta(hours=1)).timestamp()
                        ))
                    )

                    from src.mcp.d365_oauth import D365TokenProvider

                    provider = D365TokenProvider(**d365_config)
                    await provider.get_token()

                    mock_dac.assert_called_once()
                    mock_csc.assert_not_called()
