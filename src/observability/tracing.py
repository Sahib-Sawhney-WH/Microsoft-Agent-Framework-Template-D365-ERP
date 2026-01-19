"""
OpenTelemetry Tracing for the AI Assistant.

Provides distributed tracing for:
- LLM calls (tokens, latency, model)
- Tool executions (duration, success/failure)
- Workflow steps (agent transitions)
- Cache operations (hits/misses)
- Persistence operations
"""

import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, TypeVar, ParamSpec
from contextlib import contextmanager
import asyncio

import structlog

logger = structlog.get_logger(__name__)

# Type variables for generic decorators
P = ParamSpec("P")
T = TypeVar("T")

# Global tracer instance
_tracer = None
_tracing_enabled = False


@dataclass
class TracingConfig:
    """Configuration for OpenTelemetry tracing."""
    enabled: bool = False
    service_name: str = "ai-assistant"
    service_version: str = "1.0.0"

    # Exporter configuration
    exporter_type: str = "console"  # "console", "otlp", "azure", "jaeger"
    otlp_endpoint: str = "http://localhost:4317"

    # Azure Monitor specific
    azure_connection_string: str = ""

    # Sampling
    sample_rate: float = 1.0  # 1.0 = 100% sampling

    # Additional attributes
    environment: str = "development"
    additional_attributes: Dict[str, str] = field(default_factory=dict)


def setup_tracing(config: TracingConfig) -> None:
    """
    Initialize OpenTelemetry tracing.

    Args:
        config: TracingConfig with tracing settings
    """
    global _tracer, _tracing_enabled

    if not config.enabled:
        logger.info("Tracing disabled")
        _tracing_enabled = False
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        # Create resource with service info
        resource_attributes = {
            SERVICE_NAME: config.service_name,
            SERVICE_VERSION: config.service_version,
            "deployment.environment": config.environment,
            **config.additional_attributes,
        }
        resource = Resource(attributes=resource_attributes)

        # Create sampler
        sampler = TraceIdRatioBased(config.sample_rate)

        # Create and set tracer provider
        provider = TracerProvider(resource=resource, sampler=sampler)

        # Configure exporter based on type
        exporter = _create_exporter(config)
        if exporter:
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(config.service_name, config.service_version)
        _tracing_enabled = True

        logger.info(
            "Tracing initialized",
            service_name=config.service_name,
            exporter=config.exporter_type,
            sample_rate=config.sample_rate
        )

    except ImportError as e:
        logger.warning(
            "OpenTelemetry not installed, tracing disabled",
            error=str(e),
            install_hint="pip install opentelemetry-api opentelemetry-sdk"
        )
        _tracing_enabled = False
    except Exception as e:
        logger.error("Failed to initialize tracing", error=str(e))
        _tracing_enabled = False


def _create_exporter(config: TracingConfig):
    """Create the appropriate span exporter based on config."""
    exporter_type = config.exporter_type.lower()

    try:
        if exporter_type == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            return ConsoleSpanExporter()

        elif exporter_type == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            return OTLPSpanExporter(endpoint=config.otlp_endpoint)

        elif exporter_type == "azure":
            if not config.azure_connection_string:
                logger.warning("Azure connection string not provided for Azure exporter")
                return None
            from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
            return AzureMonitorTraceExporter(
                connection_string=config.azure_connection_string
            )

        elif exporter_type == "jaeger":
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter
            return JaegerExporter()

        else:
            logger.warning(f"Unknown exporter type: {exporter_type}, using console")
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            return ConsoleSpanExporter()

    except ImportError as e:
        logger.warning(f"Exporter {exporter_type} not available", error=str(e))
        return None


def get_tracer(name: str = __name__):
    """
    Get a tracer instance.

    Args:
        name: Name for the tracer (usually __name__)

    Returns:
        Tracer instance or NoOpTracer if tracing disabled
    """
    global _tracer

    if not _tracing_enabled or _tracer is None:
        # Return a no-op tracer
        return _NoOpTracer()

    return _tracer


class _NoOpTracer:
    """No-op tracer for when tracing is disabled."""

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs):
        yield _NoOpSpan()

    def start_span(self, name: str, **kwargs):
        return _NoOpSpan()


class _NoOpSpan:
    """No-op span for when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_attributes(self, attributes: Dict[str, Any]) -> None:
        pass

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def trace_async(
    span_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
):
    """
    Decorator to trace async functions.

    Args:
        span_name: Name for the span (defaults to function name)
        attributes: Additional span attributes

    Example:
        @trace_async("process_question", {"component": "agent"})
        async def process_question(self, question: str):
            ...
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            tracer = get_tracer()
            name = span_name or func.__name__

            with tracer.start_as_current_span(name) as span:
                if attributes:
                    span.set_attributes(attributes)

                # Add function arguments as attributes (sanitized)
                _add_safe_attributes(span, kwargs)

                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("success", True)
                    return result
                except Exception as e:
                    span.set_attribute("success", False)
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


def trace_sync(
    span_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
):
    """
    Decorator to trace synchronous functions.

    Args:
        span_name: Name for the span (defaults to function name)
        attributes: Additional span attributes
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            tracer = get_tracer()
            name = span_name or func.__name__

            with tracer.start_as_current_span(name) as span:
                if attributes:
                    span.set_attributes(attributes)

                _add_safe_attributes(span, kwargs)

                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("success", True)
                    return result
                except Exception as e:
                    span.set_attribute("success", False)
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


def _add_safe_attributes(span, kwargs: Dict[str, Any], max_value_length: int = 100):
    """Add kwargs as span attributes, sanitizing sensitive data."""
    sensitive_keys = {"password", "token", "secret", "key", "credential", "auth"}

    for key, value in kwargs.items():
        # Skip sensitive keys
        if any(s in key.lower() for s in sensitive_keys):
            span.set_attribute(f"arg.{key}", "[REDACTED]")
            continue

        # Convert value to string and truncate
        str_value = str(value)
        if len(str_value) > max_value_length:
            str_value = str_value[:max_value_length] + "..."

        span.set_attribute(f"arg.{key}", str_value)


# Convenience context managers for specific trace types

@contextmanager
def trace_llm_call(
    model: str,
    prompt_tokens: Optional[int] = None,
    **extra_attributes
):
    """
    Context manager for tracing LLM calls.

    Example:
        with trace_llm_call("gpt-4o", prompt_tokens=100) as span:
            result = await llm.complete(...)
            span.set_attribute("completion_tokens", result.tokens)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("llm_call") as span:
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.provider", "azure_openai")
        if prompt_tokens:
            span.set_attribute("llm.prompt_tokens", prompt_tokens)
        span.set_attributes(extra_attributes)
        yield span


@contextmanager
def trace_tool_execution(tool_name: str, **extra_attributes):
    """
    Context manager for tracing tool executions.

    Example:
        with trace_tool_execution("weather_lookup") as span:
            result = tool.run(args)
            span.set_attribute("result_length", len(result))
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("tool_execution") as span:
        span.set_attribute("tool.name", tool_name)
        span.set_attributes(extra_attributes)
        yield span


@contextmanager
def trace_workflow_step(workflow_name: str, agent_name: str, step_index: int):
    """
    Context manager for tracing workflow steps.

    Example:
        with trace_workflow_step("content-pipeline", "Researcher", 0):
            result = await agent.run(message)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("workflow_step") as span:
        span.set_attribute("workflow.name", workflow_name)
        span.set_attribute("workflow.agent", agent_name)
        span.set_attribute("workflow.step_index", step_index)
        yield span


@contextmanager
def trace_cache_operation(operation: str, cache_type: str = "redis"):
    """
    Context manager for tracing cache operations.

    Example:
        with trace_cache_operation("get", "redis") as span:
            result = await cache.get(key)
            span.set_attribute("cache.hit", result is not None)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("cache_operation") as span:
        span.set_attribute("cache.operation", operation)
        span.set_attribute("cache.type", cache_type)
        yield span
