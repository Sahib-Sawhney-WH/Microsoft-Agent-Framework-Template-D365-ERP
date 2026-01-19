"""
Secrets Management for the AI Assistant.

Provides secure access to secrets from:
- Environment variables
- Azure Key Vault
- Local configuration (development only)
"""

from src.secrets.keyvault import (
    SecretManager,
    SecretConfig,
    get_secret,
    get_secret_manager,
)

__all__ = [
    "SecretManager",
    "SecretConfig",
    "get_secret",
    "get_secret_manager",
]
