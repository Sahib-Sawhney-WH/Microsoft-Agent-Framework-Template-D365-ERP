"""
Multi-Model Provider Abstraction.

Provides support for multiple LLM providers including:
- Azure OpenAI
- OpenAI (direct)
- Anthropic Claude
- Google Gemini

Uses the Agent Framework's ChatClientProtocol abstraction for provider-agnostic
agent creation.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import structlog

logger = structlog.get_logger(__name__)


@runtime_checkable
class ChatClientProtocol(Protocol):
    """Protocol defining the chat client interface."""

    async def complete(self, messages: List[Any], **kwargs) -> Any:
        """Complete a chat conversation."""
        ...


@dataclass
class ModelProviderConfig:
    """
    Configuration for a model provider.

    Attributes:
        name: Unique identifier for this provider config (e.g., "azure_openai", "claude")
        provider: Provider type ("azure_openai", "openai", "anthropic", "gemini")
        model: Model or deployment name
        endpoint: API endpoint (for Azure)
        api_key: API key (for non-Azure providers, prefer env vars)
        api_version: API version (for Azure)
        extra_kwargs: Provider-specific options
    """

    name: str
    provider: str
    model: str
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    api_version: Optional[str] = None
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration after initialization."""
        valid_providers = {"azure_openai", "openai", "anthropic", "gemini"}
        if self.provider not in valid_providers:
            logger.warning(
                "Unknown provider type, may require custom handling",
                provider=self.provider,
                valid_providers=list(valid_providers),
            )


class ModelRegistry:
    """
    Registry of configured model providers.

    Manages multiple model configurations and provides access to them
    by name. Supports a default provider for fallback.
    """

    def __init__(self):
        """Initialize an empty registry."""
        self._providers: Dict[str, ModelProviderConfig] = {}
        self._default: Optional[str] = None

    def register(self, config: ModelProviderConfig, is_default: bool = False) -> None:
        """
        Register a model provider configuration.

        Args:
            config: The ModelProviderConfig to register
            is_default: If True, set this as the default provider
        """
        self._providers[config.name] = config
        if is_default or self._default is None:
            self._default = config.name
        logger.debug(
            "Registered model provider",
            name=config.name,
            provider=config.provider,
            model=config.model,
            is_default=is_default,
        )

    def load_from_config(self, config_list: List[Dict[str, Any]], default_model: Optional[str] = None) -> None:
        """
        Load model providers from a configuration list.

        Args:
            config_list: List of model configuration dictionaries
            default_model: Name of the default model to use

        Example config format:
            [
                {
                    "name": "azure_openai",
                    "provider": "azure_openai",
                    "endpoint": "https://...",
                    "deployment": "gpt-4o",
                    "api_version": "2024-10-01-preview"
                },
                {
                    "name": "claude",
                    "provider": "anthropic",
                    "model": "claude-3-opus-20240229"
                }
            ]
        """
        for config_dict in config_list:
            # Handle both "model" and "deployment" for Azure compatibility
            model = config_dict.get("model") or config_dict.get("deployment", "")

            provider_config = ModelProviderConfig(
                name=config_dict.get("name", config_dict.get("provider", "unnamed")),
                provider=config_dict.get("provider", "azure_openai"),
                model=model,
                endpoint=config_dict.get("endpoint"),
                api_key=config_dict.get("api_key"),
                api_version=config_dict.get("api_version"),
                extra_kwargs={
                    k: v
                    for k, v in config_dict.items()
                    if k not in {"name", "provider", "model", "deployment", "endpoint", "api_key", "api_version"}
                },
            )

            is_default = (default_model and config_dict.get("name") == default_model) or (
                not self._providers and default_model is None
            )
            self.register(provider_config, is_default=is_default)

        logger.info(
            "Loaded model providers from config",
            count=len(config_list),
            default=self._default,
        )

    def get_provider(self, name: str) -> ModelProviderConfig:
        """
        Get a provider configuration by name.

        Args:
            name: The provider name

        Returns:
            The ModelProviderConfig

        Raises:
            KeyError: If provider not found
        """
        if name not in self._providers:
            available = list(self._providers.keys())
            raise KeyError(f"Model provider '{name}' not found. Available: {available}")
        return self._providers[name]

    def get_default(self) -> ModelProviderConfig:
        """
        Get the default provider configuration.

        Returns:
            The default ModelProviderConfig

        Raises:
            ValueError: If no providers registered
        """
        if not self._default or self._default not in self._providers:
            raise ValueError("No default model provider configured")
        return self._providers[self._default]

    def list_providers(self) -> List[str]:
        """Get list of registered provider names."""
        return list(self._providers.keys())

    @property
    def default_name(self) -> Optional[str]:
        """Get the name of the default provider."""
        return self._default

    def __len__(self) -> int:
        """Return number of registered providers."""
        return len(self._providers)

    def __contains__(self, name: str) -> bool:
        """Check if a provider is registered."""
        return name in self._providers


class ModelFactory:
    """
    Factory for creating chat clients from provider configurations.

    Supports multiple providers and handles credential management
    appropriately for each provider type.
    """

    # Cached client imports to avoid repeated import attempts
    _import_cache: Dict[str, Any] = {}

    @classmethod
    def create_client(cls, config: ModelProviderConfig) -> Any:
        """
        Create a chat client based on provider configuration.

        Args:
            config: The ModelProviderConfig specifying the provider

        Returns:
            A chat client instance implementing ChatClientProtocol

        Raises:
            ImportError: If required provider library not installed
            ValueError: If provider type not supported
        """
        provider = config.provider.lower()

        if provider == "azure_openai":
            return cls._create_azure_openai_client(config)
        elif provider == "openai":
            return cls._create_openai_client(config)
        elif provider == "anthropic":
            return cls._create_anthropic_client(config)
        elif provider == "gemini":
            return cls._create_gemini_client(config)
        else:
            raise ValueError(
                f"Unsupported provider: {provider}. "
                f"Supported: azure_openai, openai, anthropic, gemini"
            )

    @classmethod
    def _create_azure_openai_client(cls, config: ModelProviderConfig) -> Any:
        """Create Azure OpenAI chat client."""
        try:
            from agent_framework.azure import AzureOpenAIChatClient
            from azure.identity import DefaultAzureCredential
        except ImportError as e:
            raise ImportError(
                "Azure OpenAI requires 'agent-framework' and 'azure-identity'. "
                f"Install with: pip install agent-framework azure-identity. Error: {e}"
            )

        endpoint = config.endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")
        if not endpoint:
            raise ValueError("Azure OpenAI requires 'endpoint' in config or AZURE_OPENAI_ENDPOINT env var")

        client = AzureOpenAIChatClient(
            endpoint=endpoint,
            deployment_name=config.model,
            credential=DefaultAzureCredential(),
            api_version=config.api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview"),
            **config.extra_kwargs,
        )

        logger.info(
            "Created Azure OpenAI client",
            endpoint=endpoint[:30] + "..." if len(endpoint) > 30 else endpoint,
            deployment=config.model,
        )
        return client

    @classmethod
    def _create_openai_client(cls, config: ModelProviderConfig) -> Any:
        """Create OpenAI direct chat client."""
        try:
            from agent_framework.openai import OpenAIChatCompletionClient
        except ImportError:
            try:
                from agent_framework import OpenAIChatCompletionClient
            except ImportError as e:
                raise ImportError(
                    "OpenAI requires 'agent-framework' with OpenAI support. "
                    f"Install with: pip install agent-framework openai. Error: {e}"
                )

        api_key = config.api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OpenAI requires 'api_key' in config or OPENAI_API_KEY env var")

        client = OpenAIChatCompletionClient(
            model=config.model,
            api_key=api_key,
            **config.extra_kwargs,
        )

        logger.info("Created OpenAI client", model=config.model)
        return client

    @classmethod
    def _create_anthropic_client(cls, config: ModelProviderConfig) -> Any:
        """Create Anthropic Claude chat client."""
        try:
            from agent_framework.anthropic import AnthropicClient
        except ImportError:
            try:
                from agent_framework import AnthropicClient
            except ImportError as e:
                raise ImportError(
                    "Anthropic requires 'agent-framework' with Anthropic support. "
                    f"Install with: pip install agent-framework anthropic. Error: {e}"
                )

        api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("Anthropic requires 'api_key' in config or ANTHROPIC_API_KEY env var")

        client = AnthropicClient(
            model=config.model,
            api_key=api_key,
            **config.extra_kwargs,
        )

        logger.info("Created Anthropic client", model=config.model)
        return client

    @classmethod
    def _create_gemini_client(cls, config: ModelProviderConfig) -> Any:
        """Create Google Gemini chat client."""
        try:
            from agent_framework.google import GeminiChatClient
        except ImportError:
            try:
                from agent_framework import GeminiChatClient
            except ImportError as e:
                raise ImportError(
                    "Gemini requires 'agent-framework' with Google support. "
                    f"Install with: pip install agent-framework google-generativeai. Error: {e}"
                )

        api_key = config.api_key or os.getenv("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("Gemini requires 'api_key' in config or GOOGLE_API_KEY env var")

        client = GeminiChatClient(
            model=config.model,
            api_key=api_key,
            **config.extra_kwargs,
        )

        logger.info("Created Gemini client", model=config.model)
        return client


def parse_model_configs(config_dict: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Parse model configurations from agent config.

    Supports two formats in TOML:

    1. Array format (recommended for multiple models):
        [[agent.models]]
        name = "azure_openai"
        provider = "azure_openai"
        endpoint = "https://..."
        deployment = "gpt-4o"

        [[agent.models]]
        name = "claude"
        provider = "anthropic"
        model = "claude-3-opus-20240229"

    2. Legacy format (single Azure OpenAI):
        [agent.azure_openai]
        endpoint = "https://..."
        deployment = "gpt-4o"

    Args:
        config_dict: The agent configuration dictionary

    Returns:
        Tuple of (list of model configs, default model name)
    """
    model_configs = []
    default_model = config_dict.get("default_model")

    # Check for new multi-model format
    models_config = config_dict.get("models", [])
    if isinstance(models_config, list) and models_config:
        model_configs = models_config
        logger.debug("Using multi-model config format", count=len(model_configs))
        return model_configs, default_model

    # Fallback to legacy Azure OpenAI format
    azure_config = config_dict.get("azure_openai", {})
    if azure_config:
        legacy_config = {
            "name": "azure_openai",
            "provider": "azure_openai",
            "endpoint": azure_config.get("endpoint", ""),
            "deployment": azure_config.get("deployment", ""),
            "api_version": azure_config.get("api_version", "2024-10-01-preview"),
        }
        model_configs = [legacy_config]
        default_model = default_model or "azure_openai"
        logger.debug("Using legacy Azure OpenAI config format")

    return model_configs, default_model
