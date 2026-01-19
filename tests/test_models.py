"""
Tests for Pydantic models.

Tests request and response models for type safety.
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError


class TestQuestionRequest:
    """Tests for QuestionRequest model."""

    def test_valid_request(self):
        """Test creating valid question request."""
        from src.models.requests import QuestionRequest

        request = QuestionRequest(
            question="How do I implement a REST API?"
        )

        assert request.question == "How do I implement a REST API?"
        assert request.chat_id is None
        assert request.stream is False

    def test_request_with_all_fields(self):
        """Test request with all optional fields."""
        from src.models.requests import QuestionRequest

        request = QuestionRequest(
            question="Test question",
            chat_id="chat-123",
            stream=True,
            max_tokens=1000,
            temperature=0.7
        )

        assert request.chat_id == "chat-123"
        assert request.stream is True
        assert request.max_tokens == 1000
        assert request.temperature == 0.7

    def test_request_validation_empty_question(self):
        """Test that empty question is rejected."""
        from src.models.requests import QuestionRequest

        with pytest.raises(ValidationError):
            QuestionRequest(question="")

    def test_request_validation_temperature_range(self):
        """Test temperature validation."""
        from src.models.requests import QuestionRequest

        # Valid temperature
        request = QuestionRequest(question="test", temperature=1.0)
        assert request.temperature == 1.0

        # Invalid temperatures should be validated by the model


class TestWorkflowRequest:
    """Tests for WorkflowRequest model."""

    def test_valid_workflow_request(self):
        """Test creating valid workflow request."""
        from src.models.requests import WorkflowRequest

        request = WorkflowRequest(
            workflow_name="content-pipeline",
            message="Create a blog post about AI"
        )

        assert request.workflow_name == "content-pipeline"
        assert request.message == "Create a blog post about AI"
        assert request.stream is False


class TestQuestionResponse:
    """Tests for QuestionResponse model."""

    def test_successful_response(self):
        """Test creating successful response."""
        from src.models.responses import QuestionResponse

        response = QuestionResponse(
            question="What is Python?",
            response="Python is a programming language...",
            success=True,
            chat_id="chat-123"
        )

        assert response.success is True
        assert response.chat_id == "chat-123"
        assert response.error is None

    def test_response_with_metrics(self):
        """Test response with usage metrics."""
        from src.models.responses import QuestionResponse

        response = QuestionResponse(
            question="Test",
            response="Answer",
            success=True,
            chat_id="chat-123",
            tokens_used=150,
            latency_ms=1234.5,
            tool_calls=["search", "compute"]
        )

        assert response.tokens_used == 150
        assert response.latency_ms == 1234.5
        assert len(response.tool_calls) == 2

    def test_failed_response(self):
        """Test creating failed response."""
        from src.models.responses import QuestionResponse

        response = QuestionResponse(
            question="Test",
            response="",
            success=False,
            chat_id="chat-123",
            error="Rate limit exceeded"
        )

        assert response.success is False
        assert response.error == "Rate limit exceeded"


class TestStreamChunk:
    """Tests for StreamChunk model."""

    def test_text_chunk(self):
        """Test creating text chunk."""
        from src.models.responses import StreamChunk

        chunk = StreamChunk(
            text="Hello ",
            done=False,
            chat_id="chat-123"
        )

        assert chunk.text == "Hello "
        assert chunk.done is False

    def test_final_chunk(self):
        """Test creating final chunk."""
        from src.models.responses import StreamChunk

        chunk = StreamChunk(
            text="",
            done=True,
            chat_id="chat-123"
        )

        assert chunk.done is True

    def test_chunk_with_tool_calls(self):
        """Test chunk with tool call notifications."""
        from src.models.responses import StreamChunk

        chunk = StreamChunk(
            text="Searching...",
            done=False,
            chat_id="chat-123",
            tool_calls=["web_search"]
        )

        assert "web_search" in chunk.tool_calls


class TestWorkflowResponse:
    """Tests for WorkflowResponse model."""

    def test_successful_workflow(self):
        """Test successful workflow response."""
        from src.models.responses import WorkflowResponse

        response = WorkflowResponse(
            workflow="content-pipeline",
            message="Create article",
            response="Article content here...",
            success=True,
            author="Writer Agent"
        )

        assert response.workflow == "content-pipeline"
        assert response.success is True
        assert response.author == "Writer Agent"

    def test_workflow_with_steps(self):
        """Test workflow response with step details."""
        from src.models.responses import WorkflowResponse

        response = WorkflowResponse(
            workflow="content-pipeline",
            message="Create article",
            response="Final output",
            success=True,
            steps=[
                {"agent": "Researcher", "output": "Research done"},
                {"agent": "Writer", "output": "Draft written"}
            ]
        )

        assert len(response.steps) == 2


class TestHealthResponse:
    """Tests for HealthResponse model."""

    def test_healthy_response(self):
        """Test healthy status response."""
        from src.models.responses import HealthResponse, ComponentHealth

        response = HealthResponse(
            status="healthy",
            timestamp=datetime.now(timezone.utc),
            version="1.0.0",
            uptime_seconds=3600.0,
            components=[
                ComponentHealth(
                    name="redis",
                    status="healthy",
                    latency_ms=5.0
                )
            ]
        )

        assert response.status == "healthy"
        assert len(response.components) == 1

    def test_degraded_response(self):
        """Test degraded status response."""
        from src.models.responses import HealthResponse, ComponentHealth

        response = HealthResponse(
            status="degraded",
            timestamp=datetime.now(timezone.utc),
            version="1.0.0",
            uptime_seconds=3600.0,
            components=[
                ComponentHealth(
                    name="redis",
                    status="degraded",
                    latency_ms=500.0,
                    message="High latency"
                )
            ]
        )

        assert response.status == "degraded"
        assert response.components[0].message == "High latency"


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_error_response(self):
        """Test error response creation."""
        from src.models.responses import ErrorResponse

        response = ErrorResponse(
            error="Rate limit exceeded",
            error_type="RateLimitError",
            request_id="req-123"
        )

        assert response.error == "Rate limit exceeded"
        assert response.error_type == "RateLimitError"

    def test_error_with_details(self):
        """Test error response with details."""
        from src.models.responses import ErrorResponse

        response = ErrorResponse(
            error="Validation failed",
            error_type="ValidationError",
            details={"field": "question", "reason": "too long"}
        )

        assert response.details["field"] == "question"


class TestChatListItem:
    """Tests for ChatListItem model."""

    def test_chat_list_item(self):
        """Test chat list item creation."""
        from src.models.responses import ChatListItem

        item = ChatListItem(
            chat_id="chat-123",
            active=True,
            created_at=datetime.now(timezone.utc),
            message_count=10,
            persisted=True
        )

        assert item.chat_id == "chat-123"
        assert item.active is True
        assert item.message_count == 10


class TestConfigModels:
    """Tests for configuration models."""

    def test_observability_config(self):
        """Test observability config model."""
        from src.models.config import ObservabilityConfig

        config = ObservabilityConfig(
            tracing_enabled=True,
            metrics_enabled=True,
            service_name="test-service"
        )

        assert config.tracing_enabled is True
        assert config.service_name == "test-service"

    def test_security_config(self):
        """Test security config model."""
        from src.models.config import SecurityConfig

        config = SecurityConfig(
            rate_limit_enabled=True,
            input_validation_enabled=True,
            requests_per_minute=60
        )

        assert config.rate_limit_enabled is True
        assert config.requests_per_minute == 60


class TestModelProviderConfig:
    """Tests for ModelProviderConfig dataclass."""

    def test_azure_openai_config(self):
        """Test creating Azure OpenAI provider config."""
        from src.models.providers import ModelProviderConfig

        config = ModelProviderConfig(
            name="azure_openai",
            provider="azure_openai",
            model="gpt-4o",
            endpoint="https://test.openai.azure.com/",
            api_version="2024-10-01-preview"
        )

        assert config.name == "azure_openai"
        assert config.provider == "azure_openai"
        assert config.model == "gpt-4o"
        assert config.endpoint == "https://test.openai.azure.com/"

    def test_anthropic_config(self):
        """Test creating Anthropic provider config."""
        from src.models.providers import ModelProviderConfig

        config = ModelProviderConfig(
            name="claude",
            provider="anthropic",
            model="claude-3-opus-20240229"
        )

        assert config.name == "claude"
        assert config.provider == "anthropic"
        assert config.model == "claude-3-opus-20240229"

    def test_extra_kwargs(self):
        """Test config with extra kwargs."""
        from src.models.providers import ModelProviderConfig

        config = ModelProviderConfig(
            name="custom",
            provider="openai",
            model="gpt-4",
            extra_kwargs={"temperature": 0.7, "max_tokens": 1000}
        )

        assert config.extra_kwargs["temperature"] == 0.7
        assert config.extra_kwargs["max_tokens"] == 1000


class TestModelRegistry:
    """Tests for ModelRegistry class."""

    def test_register_provider(self):
        """Test registering a provider."""
        from src.models.providers import ModelRegistry, ModelProviderConfig

        registry = ModelRegistry()
        config = ModelProviderConfig(
            name="test_provider",
            provider="azure_openai",
            model="gpt-4o"
        )

        registry.register(config, is_default=True)

        assert "test_provider" in registry
        assert len(registry) == 1
        assert registry.default_name == "test_provider"

    def test_get_provider(self):
        """Test getting a registered provider."""
        from src.models.providers import ModelRegistry, ModelProviderConfig

        registry = ModelRegistry()
        config = ModelProviderConfig(
            name="my_provider",
            provider="openai",
            model="gpt-4"
        )
        registry.register(config)

        retrieved = registry.get_provider("my_provider")
        assert retrieved.name == "my_provider"
        assert retrieved.model == "gpt-4"

    def test_get_provider_not_found(self):
        """Test getting non-existent provider raises KeyError."""
        from src.models.providers import ModelRegistry

        registry = ModelRegistry()

        with pytest.raises(KeyError):
            registry.get_provider("nonexistent")

    def test_get_default(self):
        """Test getting default provider."""
        from src.models.providers import ModelRegistry, ModelProviderConfig

        registry = ModelRegistry()
        config1 = ModelProviderConfig(name="first", provider="azure_openai", model="gpt-4o")
        config2 = ModelProviderConfig(name="second", provider="openai", model="gpt-4")

        registry.register(config1)
        registry.register(config2, is_default=True)

        default = registry.get_default()
        assert default.name == "second"

    def test_list_providers(self):
        """Test listing all provider names."""
        from src.models.providers import ModelRegistry, ModelProviderConfig

        registry = ModelRegistry()
        registry.register(ModelProviderConfig(name="provider1", provider="azure_openai", model="gpt-4o"))
        registry.register(ModelProviderConfig(name="provider2", provider="openai", model="gpt-4"))

        providers = registry.list_providers()
        assert "provider1" in providers
        assert "provider2" in providers
        assert len(providers) == 2

    def test_load_from_config(self):
        """Test loading providers from config list."""
        from src.models.providers import ModelRegistry

        registry = ModelRegistry()
        config_list = [
            {
                "name": "azure_openai",
                "provider": "azure_openai",
                "endpoint": "https://test.openai.azure.com/",
                "deployment": "gpt-4o",
                "api_version": "2024-10-01-preview"
            },
            {
                "name": "claude",
                "provider": "anthropic",
                "model": "claude-3-opus-20240229"
            }
        ]

        registry.load_from_config(config_list, default_model="azure_openai")

        assert len(registry) == 2
        assert registry.default_name == "azure_openai"
        assert registry.get_provider("claude").model == "claude-3-opus-20240229"


class TestParseModelConfigs:
    """Tests for parse_model_configs function."""

    def test_parse_multi_model_config(self):
        """Test parsing multi-model config format."""
        from src.models.providers import parse_model_configs

        config_dict = {
            "default_model": "azure_openai",
            "models": [
                {
                    "name": "azure_openai",
                    "provider": "azure_openai",
                    "endpoint": "https://test.openai.azure.com/",
                    "deployment": "gpt-4o"
                },
                {
                    "name": "claude",
                    "provider": "anthropic",
                    "model": "claude-3-opus"
                }
            ]
        }

        model_configs, default_model = parse_model_configs(config_dict)

        assert len(model_configs) == 2
        assert default_model == "azure_openai"

    def test_parse_legacy_config(self):
        """Test parsing legacy Azure OpenAI config format."""
        from src.models.providers import parse_model_configs

        config_dict = {
            "azure_openai": {
                "endpoint": "https://test.openai.azure.com/",
                "deployment": "gpt-4o",
                "api_version": "2024-10-01-preview"
            }
        }

        model_configs, default_model = parse_model_configs(config_dict)

        assert len(model_configs) == 1
        assert model_configs[0]["name"] == "azure_openai"
        assert model_configs[0]["deployment"] == "gpt-4o"

    def test_parse_empty_config(self):
        """Test parsing empty config."""
        from src.models.providers import parse_model_configs

        model_configs, default_model = parse_model_configs({})

        assert len(model_configs) == 0
        assert default_model is None


class TestMCPSessionConfig:
    """Tests for MCP session configuration."""

    def test_mcp_session_config_defaults(self):
        """Test MCPSessionConfig with defaults."""
        from src.mcp.session import MCPSessionConfig

        config = MCPSessionConfig()

        assert config.enabled is False
        assert config.session_ttl == 3600
        assert config.persist_sessions is True
        assert config.cache_prefix == "mcp_session:"

    def test_mcp_session_config_custom(self):
        """Test MCPSessionConfig with custom values."""
        from src.mcp.session import MCPSessionConfig

        config = MCPSessionConfig(
            enabled=True,
            session_ttl=7200,
            persist_sessions=False,
            cache_prefix="custom_prefix:"
        )

        assert config.enabled is True
        assert config.session_ttl == 7200
        assert config.persist_sessions is False
        assert config.cache_prefix == "custom_prefix:"


class TestMCPSessionState:
    """Tests for MCPSessionState dataclass."""

    def test_session_state_creation(self):
        """Test creating MCP session state."""
        from src.mcp.session import MCPSessionState

        session = MCPSessionState(
            session_id="sess-123",
            chat_id="chat-456",
            mcp_server_name="d365-erp",
            user_id="user@test.com"
        )

        assert session.session_id == "sess-123"
        assert session.chat_id == "chat-456"
        assert session.mcp_server_name == "d365-erp"
        assert session.user_id == "user@test.com"
        assert session.form_context == {}

    def test_session_state_to_dict(self):
        """Test serializing session state to dict."""
        from src.mcp.session import MCPSessionState

        session = MCPSessionState(
            session_id="sess-123",
            chat_id="chat-456",
            mcp_server_name="d365-erp"
        )

        data = session.to_dict()

        assert data["session_id"] == "sess-123"
        assert data["chat_id"] == "chat-456"
        assert data["mcp_server_name"] == "d365-erp"
        assert "created_at" in data
        assert "last_accessed" in data

    def test_session_state_from_dict(self):
        """Test deserializing session state from dict."""
        from src.mcp.session import MCPSessionState
        from datetime import datetime, timezone

        data = {
            "session_id": "sess-789",
            "chat_id": "chat-abc",
            "mcp_server_name": "test-server",
            "user_id": "test@user.com",
            "form_context": {"form": "data"},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_accessed": datetime.now(timezone.utc).isoformat(),
            "metadata": {"key": "value"}
        }

        session = MCPSessionState.from_dict(data)

        assert session.session_id == "sess-789"
        assert session.form_context == {"form": "data"}
        assert session.metadata == {"key": "value"}


class TestParseMCPSessionConfig:
    """Tests for parse_mcp_session_config function."""

    def test_parse_enabled_config(self):
        """Test parsing enabled MCP session config."""
        from src.mcp.session import parse_mcp_session_config

        config_dict = {
            "mcp_sessions": {
                "enabled": True,
                "session_ttl": 1800,
                "persist_sessions": False
            }
        }

        config = parse_mcp_session_config(config_dict)

        assert config.enabled is True
        assert config.session_ttl == 1800
        assert config.persist_sessions is False

    def test_parse_missing_config(self):
        """Test parsing when mcp_sessions section is missing."""
        from src.mcp.session import parse_mcp_session_config

        config = parse_mcp_session_config({})

        assert config.enabled is False
        assert config.session_ttl == 3600
