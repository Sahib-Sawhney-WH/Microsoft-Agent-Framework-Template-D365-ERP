"""
Tests for the observability module.

Tests tracing and metrics functionality.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestTracingConfig:
    """Tests for TracingConfig."""

    def test_default_config(self):
        """Test default tracing configuration."""
        from src.observability.tracing import TracingConfig

        config = TracingConfig()
        assert config.enabled is True
        assert config.service_name == "ai-assistant"
        assert config.exporter_type == "console"
        assert config.sample_rate == 1.0

    def test_custom_config(self):
        """Test custom tracing configuration."""
        from src.observability.tracing import TracingConfig

        config = TracingConfig(
            enabled=False,
            service_name="test-service",
            exporter_type="otlp",
            otlp_endpoint="http://localhost:4317",
            sample_rate=0.5
        )
        assert config.enabled is False
        assert config.service_name == "test-service"
        assert config.otlp_endpoint == "http://localhost:4317"
        assert config.sample_rate == 0.5


class TestTracer:
    """Tests for tracer functionality."""

    def test_get_tracer_returns_noop_when_disabled(self):
        """Test that NoOp tracer is returned when tracing is disabled."""
        from src.observability.tracing import setup_tracing, get_tracer, TracingConfig

        config = TracingConfig(enabled=False)
        setup_tracing(config)

        tracer = get_tracer()
        # NoOp tracer should still work
        assert tracer is not None

    def test_get_tracer_returns_tracer(self):
        """Test that tracer is returned when enabled."""
        from src.observability.tracing import setup_tracing, get_tracer, TracingConfig

        config = TracingConfig(enabled=True, exporter_type="none")
        setup_tracing(config)

        tracer = get_tracer()
        assert tracer is not None


class TestTracingDecorators:
    """Tests for tracing decorators."""

    def test_trace_sync_decorator(self):
        """Test sync tracing decorator."""
        from src.observability.tracing import trace_sync

        @trace_sync("test_operation")
        def sample_function(x, y):
            return x + y

        result = sample_function(1, 2)
        assert result == 3

    @pytest.mark.asyncio
    async def test_trace_async_decorator(self):
        """Test async tracing decorator."""
        from src.observability.tracing import trace_async

        @trace_async("test_async_operation")
        async def sample_async_function(x, y):
            return x * y

        result = await sample_async_function(3, 4)
        assert result == 12


class TestTracingContextManagers:
    """Tests for tracing context managers."""

    @pytest.mark.asyncio
    async def test_trace_llm_call(self):
        """Test LLM call tracing context manager."""
        from src.observability.tracing import trace_llm_call

        async with trace_llm_call("gpt-4", prompt_tokens=100, completion_tokens=50):
            # Simulate LLM call
            pass

    @pytest.mark.asyncio
    async def test_trace_tool_execution(self):
        """Test tool execution tracing context manager."""
        from src.observability.tracing import trace_tool_execution

        async with trace_tool_execution("test_tool", {"param": "value"}):
            # Simulate tool execution
            pass

    @pytest.mark.asyncio
    async def test_trace_workflow_step(self):
        """Test workflow step tracing context manager."""
        from src.observability.tracing import trace_workflow_step

        async with trace_workflow_step("test_workflow", "step_1", "agent_1"):
            # Simulate workflow step
            pass


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_metrics_collector_initialization(self):
        """Test metrics collector initialization."""
        from src.observability.metrics import MetricsCollector

        collector = MetricsCollector(service_name="test-service")
        assert collector is not None

    def test_record_request(self):
        """Test recording request metrics."""
        from src.observability.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.record_request(100.5, success=True, chat_id="test-123")
        collector.record_request(50.0, success=False, chat_id="test-456")

        # Metrics should be recorded without error

    def test_record_tool_call(self):
        """Test recording tool call metrics."""
        from src.observability.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.record_tool_call("search", 200.0, success=True)
        collector.record_tool_call("compute", 500.0, success=False)

    def test_record_error(self):
        """Test recording error metrics."""
        from src.observability.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.record_error("ValidationError", "input_validation")
        collector.record_error("TimeoutError", "llm_call")

    def test_record_cache_access(self):
        """Test recording cache access metrics."""
        from src.observability.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.record_cache_access(hit=True)
        collector.record_cache_access(hit=False)

    def test_record_tokens(self):
        """Test recording token usage metrics."""
        from src.observability.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.record_tokens(
            prompt_tokens=100,
            completion_tokens=50,
            model="gpt-4"
        )

    def test_get_summary(self):
        """Test getting metrics summary."""
        from src.observability.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.record_request(100.0, success=True)
        collector.record_request(50.0, success=False)
        collector.record_tool_call("test", 25.0, success=True)

        summary = collector.get_summary()
        assert "total_requests" in summary
        assert "successful_requests" in summary
        assert "failed_requests" in summary


class TestMetricsModule:
    """Tests for metrics module functions."""

    def test_setup_and_get_metrics(self):
        """Test setup_metrics and get_metrics functions."""
        from src.observability.metrics import setup_metrics, get_metrics

        setup_metrics(service_name="test-service")
        metrics = get_metrics()

        assert metrics is not None
        metrics.record_request(100.0, success=True)
