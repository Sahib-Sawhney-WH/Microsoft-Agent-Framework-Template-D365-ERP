"""
Observability module for the AI Assistant.

Provides OpenTelemetry integration for distributed tracing,
metrics collection, and structured logging.
"""

from src.observability.tracing import (
    setup_tracing,
    get_tracer,
    TracingConfig,
    trace_async,
    trace_sync,
)
from src.observability.metrics import (
    setup_metrics,
    MetricsCollector,
    get_metrics,
)

__all__ = [
    "setup_tracing",
    "get_tracer",
    "TracingConfig",
    "trace_async",
    "trace_sync",
    "setup_metrics",
    "MetricsCollector",
    "get_metrics",
]
