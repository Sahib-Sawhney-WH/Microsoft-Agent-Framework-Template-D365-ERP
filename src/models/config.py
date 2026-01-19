"""
Configuration models for the AI Assistant.

Provides type-safe configuration validation.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class ObservabilityConfig(BaseModel):
    """Configuration for observability features."""

    # Tracing
    tracing_enabled: bool = Field(False, description="Enable OpenTelemetry tracing")
    tracing_exporter: str = Field("console", description="Trace exporter type")
    tracing_endpoint: str = Field("", description="OTLP endpoint for traces")
    tracing_sample_rate: float = Field(1.0, ge=0.0, le=1.0, description="Trace sample rate")

    # Metrics
    metrics_enabled: bool = Field(False, description="Enable metrics collection")
    metrics_exporter: str = Field("console", description="Metrics exporter type")
    metrics_port: int = Field(8000, ge=1, le=65535, description="Prometheus metrics port")

    # Azure Monitor
    azure_connection_string: str = Field("", description="Azure Monitor connection string")

    # Service info
    service_name: str = Field("ai-assistant", description="Service name for telemetry")
    service_version: str = Field("1.0.0", description="Service version")
    environment: str = Field("development", description="Deployment environment")

    class Config:
        json_schema_extra = {
            "example": {
                "tracing_enabled": True,
                "tracing_exporter": "azure",
                "metrics_enabled": True,
                "metrics_exporter": "prometheus",
                "service_name": "my-ai-assistant",
                "environment": "production"
            }
        }


class SecurityConfig(BaseModel):
    """Configuration for security features."""

    # Rate limiting
    rate_limit_enabled: bool = Field(True, description="Enable rate limiting")
    rate_limit_requests_per_minute: int = Field(60, ge=1, description="Max requests per minute")
    rate_limit_tokens_per_minute: int = Field(100000, ge=1, description="Max tokens per minute")

    # Input validation
    max_question_length: int = Field(32000, ge=100, description="Max question length")
    max_tool_calls_per_request: int = Field(10, ge=1, description="Max tool calls per request")

    # Content filtering
    block_prompt_injection: bool = Field(True, description="Block potential prompt injections")
    block_pii: bool = Field(False, description="Block PII in inputs")
    allowed_tool_names: Optional[List[str]] = Field(None, description="Whitelist of allowed tools")
    blocked_tool_names: List[str] = Field(default_factory=list, description="Blacklist of blocked tools")

    # Authentication (for future use)
    require_authentication: bool = Field(False, description="Require auth for requests")
    allowed_origins: List[str] = Field(default_factory=list, description="CORS allowed origins")

    class Config:
        json_schema_extra = {
            "example": {
                "rate_limit_enabled": True,
                "rate_limit_requests_per_minute": 60,
                "block_prompt_injection": True,
                "blocked_tool_names": ["dangerous_tool"]
            }
        }


class MemoryConfigModel(BaseModel):
    """Configuration for memory/session management."""

    # Cache settings
    cache_enabled: bool = Field(False, description="Enable Redis cache")
    cache_host: str = Field("", description="Redis host")
    cache_port: int = Field(6380, description="Redis port")
    cache_ssl: bool = Field(True, description="Use SSL for Redis")
    cache_ttl: int = Field(3600, ge=60, description="Cache TTL in seconds")
    cache_prefix: str = Field("chat:", description="Key prefix")

    # Persistence settings
    persistence_enabled: bool = Field(False, description="Enable ADLS persistence")
    persistence_account: str = Field("", description="Storage account name")
    persistence_container: str = Field("chat-history", description="Container name")
    persistence_folder: str = Field("threads", description="Folder path")
    persistence_schedule: str = Field("ttl+300", description="Persist schedule")

    # Summarization
    summarization_enabled: bool = Field(False, description="Enable context summarization")
    summarization_threshold_tokens: int = Field(4000, description="Token threshold for summarization")
    summarization_keep_recent: int = Field(5, description="Recent messages to keep after summarization")


class D365OAuthConfig(BaseModel):
    """
    D365 OAuth configuration.

    Supports both DefaultAzureCredential (when no credentials provided)
    and ClientSecretCredential (when all credentials provided).
    """

    environment_url: str = Field(..., description="D365 F&O environment URL")
    tenant_id: Optional[str] = Field(None, description="Azure AD tenant ID")
    client_id: Optional[str] = Field(None, description="App registration client ID")
    client_secret: Optional[str] = Field(None, description="App registration secret")
    token_refresh_buffer_minutes: int = Field(
        5, ge=1, le=30, description="Minutes before expiry to refresh token"
    )

    @model_validator(mode="after")
    def validate_credentials(self) -> "D365OAuthConfig":
        """If any credential provided, all must be provided."""
        creds = [self.tenant_id, self.client_id, self.client_secret]
        if any(creds) and not all(creds):
            raise ValueError(
                "If providing credentials, tenant_id, client_id, and client_secret are all required"
            )
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "environment_url": "https://myorg.operations.dynamics.com",
                "tenant_id": "your-tenant-id",
                "client_id": "your-client-id",
                "client_secret": "${D365_CLIENT_SECRET}",
                "token_refresh_buffer_minutes": 5,
            }
        }


class D365MCPConfig(BaseModel):
    """
    D365 MCP tool configuration.

    Includes OAuth settings, timeout configuration (following SDK pattern),
    retry configuration, and health check settings.
    """

    name: str = Field("d365-fo", description="Tool name")
    enabled: bool = Field(True, description="Enable this MCP")
    description: str = Field(
        "D365 Finance & Operations", description="Tool description"
    )
    oauth: D365OAuthConfig

    # Timeout configuration (following SDK pattern)
    timeout_connect: float = Field(10.0, ge=1.0, description="Connection timeout seconds")
    timeout_read: float = Field(60.0, ge=10.0, description="Read timeout seconds")
    timeout_write: float = Field(10.0, ge=1.0, description="Write timeout seconds")
    timeout_pool: float = Field(5.0, ge=1.0, description="Pool timeout seconds")

    # Retry configuration
    max_retries: int = Field(3, ge=0, le=10, description="Max retry attempts")
    retry_backoff_base: float = Field(
        1.0, ge=0.5, description="Exponential backoff base seconds"
    )
    retry_backoff_max: float = Field(30.0, ge=5.0, description="Max backoff seconds")

    # Health check
    health_check_enabled: bool = Field(True, description="Enable health checks")
    health_check_interval: int = Field(
        60, ge=10, description="Health check interval seconds"
    )

    # Circuit breaker
    circuit_breaker_failure_threshold: int = Field(
        5, ge=1, le=20, description="Failures before opening circuit"
    )
    circuit_breaker_recovery_timeout: float = Field(
        30.0, ge=5.0, description="Seconds before attempting recovery"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "d365-fo",
                "enabled": True,
                "description": "D365 Finance & Operations",
                "oauth": {
                    "environment_url": "https://myorg.operations.dynamics.com",
                    "tenant_id": "your-tenant-id",
                    "client_id": "your-client-id",
                    "client_secret": "${D365_CLIENT_SECRET}",
                },
                "timeout_connect": 10.0,
                "timeout_read": 60.0,
                "max_retries": 3,
            }
        }
