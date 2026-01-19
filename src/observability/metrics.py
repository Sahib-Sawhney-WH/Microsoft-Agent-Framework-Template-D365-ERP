"""
Metrics Collection for the AI Assistant.

Provides metrics for:
- Request latency histograms
- Tool call counters
- Error rate gauges
- Cache hit ratio
- Token usage
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time
from contextlib import contextmanager

import structlog

logger = structlog.get_logger(__name__)

# Global metrics collector
_metrics_collector: Optional["MetricsCollector"] = None


@dataclass
class MetricsConfig:
    """Configuration for metrics collection."""
    enabled: bool = False
    exporter_type: str = "console"  # "console", "prometheus", "azure"
    prometheus_port: int = 8000
    azure_connection_string: str = ""
    service_name: str = "ai-assistant"
    collection_interval: int = 60  # seconds


def setup_metrics(config: MetricsConfig) -> "MetricsCollector":
    """
    Initialize metrics collection.

    Args:
        config: MetricsConfig with metrics settings

    Returns:
        MetricsCollector instance
    """
    global _metrics_collector

    if not config.enabled:
        logger.info("Metrics collection disabled")
        _metrics_collector = MetricsCollector(enabled=False)
        return _metrics_collector

    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME

        # Create resource
        resource = Resource(attributes={SERVICE_NAME: config.service_name})

        # Create meter provider with exporter
        exporter = _create_metrics_exporter(config)
        if exporter:
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            reader = PeriodicExportingMetricReader(
                exporter,
                export_interval_millis=config.collection_interval * 1000
            )
            provider = MeterProvider(resource=resource, metric_readers=[reader])
        else:
            provider = MeterProvider(resource=resource)

        metrics.set_meter_provider(provider)
        meter = metrics.get_meter(config.service_name)

        _metrics_collector = MetricsCollector(enabled=True, meter=meter)

        logger.info(
            "Metrics collection initialized",
            exporter=config.exporter_type,
            interval=config.collection_interval
        )

        return _metrics_collector

    except ImportError as e:
        logger.warning(
            "OpenTelemetry metrics not installed",
            error=str(e),
            install_hint="pip install opentelemetry-api opentelemetry-sdk"
        )
        _metrics_collector = MetricsCollector(enabled=False)
        return _metrics_collector
    except Exception as e:
        logger.error("Failed to initialize metrics", error=str(e))
        _metrics_collector = MetricsCollector(enabled=False)
        return _metrics_collector


def _create_metrics_exporter(config: MetricsConfig):
    """Create the appropriate metrics exporter based on config."""
    exporter_type = config.exporter_type.lower()

    try:
        if exporter_type == "console":
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
            return ConsoleMetricExporter()

        elif exporter_type == "prometheus":
            from opentelemetry.exporter.prometheus import PrometheusMetricReader
            # Note: Prometheus uses a pull model, handled differently
            logger.info(f"Prometheus metrics available on port {config.prometheus_port}")
            return None

        elif exporter_type == "azure":
            if not config.azure_connection_string:
                logger.warning("Azure connection string not provided")
                return None
            from azure.monitor.opentelemetry.exporter import AzureMonitorMetricExporter
            return AzureMonitorMetricExporter(
                connection_string=config.azure_connection_string
            )

        elif exporter_type == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            return OTLPMetricExporter()

        else:
            logger.warning(f"Unknown metrics exporter: {exporter_type}")
            return None

    except ImportError as e:
        logger.warning(f"Metrics exporter {exporter_type} not available", error=str(e))
        return None


def get_metrics() -> "MetricsCollector":
    """Get the global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector(enabled=False)
    return _metrics_collector


class MetricsCollector:
    """
    Collects and records metrics for the AI Assistant.

    Provides counters, histograms, and gauges for monitoring.
    Falls back to in-memory tracking if OpenTelemetry not available.
    """

    def __init__(self, enabled: bool = False, meter: Any = None):
        """
        Initialize metrics collector.

        Args:
            enabled: Whether metrics collection is enabled
            meter: OpenTelemetry meter instance
        """
        self.enabled = enabled
        self._meter = meter

        # In-memory fallback metrics
        self._counters: Dict[str, int] = {}
        self._histograms: Dict[str, list] = {}
        self._gauges: Dict[str, float] = {}

        # Initialize OpenTelemetry instruments if available
        if self.enabled and self._meter:
            self._init_instruments()
        else:
            self._request_counter = None
            self._request_latency = None
            self._tool_counter = None
            self._tool_latency = None
            self._error_counter = None
            self._cache_hit_counter = None
            self._cache_miss_counter = None
            self._token_counter = None
            self._active_sessions = None

    def _init_instruments(self):
        """Initialize OpenTelemetry metric instruments."""
        # Request metrics
        self._request_counter = self._meter.create_counter(
            "ai_assistant.requests",
            description="Total number of requests processed",
            unit="1"
        )

        self._request_latency = self._meter.create_histogram(
            "ai_assistant.request_latency",
            description="Request processing latency",
            unit="ms"
        )

        # Tool metrics
        self._tool_counter = self._meter.create_counter(
            "ai_assistant.tool_calls",
            description="Total number of tool calls",
            unit="1"
        )

        self._tool_latency = self._meter.create_histogram(
            "ai_assistant.tool_latency",
            description="Tool execution latency",
            unit="ms"
        )

        # Error metrics
        self._error_counter = self._meter.create_counter(
            "ai_assistant.errors",
            description="Total number of errors",
            unit="1"
        )

        # Cache metrics
        self._cache_hit_counter = self._meter.create_counter(
            "ai_assistant.cache_hits",
            description="Cache hit count",
            unit="1"
        )

        self._cache_miss_counter = self._meter.create_counter(
            "ai_assistant.cache_misses",
            description="Cache miss count",
            unit="1"
        )

        # Token metrics
        self._token_counter = self._meter.create_counter(
            "ai_assistant.tokens",
            description="Total tokens used",
            unit="1"
        )

        # Session metrics
        self._active_sessions = self._meter.create_up_down_counter(
            "ai_assistant.active_sessions",
            description="Number of active sessions",
            unit="1"
        )

    def record_request(
        self,
        latency_ms: float,
        success: bool = True,
        chat_id: Optional[str] = None,
        workflow: Optional[str] = None
    ):
        """
        Record a request metric.

        Args:
            latency_ms: Request latency in milliseconds
            success: Whether the request succeeded
            chat_id: Optional chat session ID
            workflow: Optional workflow name if this was a workflow request
        """
        attributes = {
            "success": str(success).lower(),
            "type": "workflow" if workflow else "question"
        }

        if self.enabled and self._request_counter:
            self._request_counter.add(1, attributes)
            self._request_latency.record(latency_ms, attributes)
        else:
            # Fallback
            key = f"requests.{attributes['type']}.{attributes['success']}"
            self._counters[key] = self._counters.get(key, 0) + 1
            self._histograms.setdefault("request_latency", []).append(latency_ms)

    def record_tool_call(
        self,
        tool_name: str,
        latency_ms: float,
        success: bool = True
    ):
        """Record a tool call metric."""
        attributes = {
            "tool": tool_name,
            "success": str(success).lower()
        }

        if self.enabled and self._tool_counter:
            self._tool_counter.add(1, attributes)
            self._tool_latency.record(latency_ms, attributes)
        else:
            key = f"tools.{tool_name}.{attributes['success']}"
            self._counters[key] = self._counters.get(key, 0) + 1
            self._histograms.setdefault(f"tool_latency.{tool_name}", []).append(latency_ms)

    def record_error(
        self,
        error_type: str,
        component: str = "unknown"
    ):
        """Record an error metric."""
        attributes = {
            "error_type": error_type,
            "component": component
        }

        if self.enabled and self._error_counter:
            self._error_counter.add(1, attributes)
        else:
            key = f"errors.{component}.{error_type}"
            self._counters[key] = self._counters.get(key, 0) + 1

    def record_cache_access(self, hit: bool, cache_type: str = "redis"):
        """Record a cache access metric."""
        attributes = {"cache_type": cache_type}

        if self.enabled:
            if hit and self._cache_hit_counter:
                self._cache_hit_counter.add(1, attributes)
            elif not hit and self._cache_miss_counter:
                self._cache_miss_counter.add(1, attributes)
        else:
            key = f"cache.{cache_type}.{'hit' if hit else 'miss'}"
            self._counters[key] = self._counters.get(key, 0) + 1

    def record_tokens(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: str = "unknown"
    ):
        """Record token usage metrics."""
        if self.enabled and self._token_counter:
            self._token_counter.add(prompt_tokens, {"type": "prompt", "model": model})
            self._token_counter.add(completion_tokens, {"type": "completion", "model": model})
        else:
            self._counters["tokens.prompt"] = self._counters.get("tokens.prompt", 0) + prompt_tokens
            self._counters["tokens.completion"] = self._counters.get("tokens.completion", 0) + completion_tokens

    def record_session_start(self):
        """Record a new session starting."""
        if self.enabled and self._active_sessions:
            self._active_sessions.add(1)
        else:
            self._gauges["active_sessions"] = self._gauges.get("active_sessions", 0) + 1

    def record_session_end(self):
        """Record a session ending."""
        if self.enabled and self._active_sessions:
            self._active_sessions.add(-1)
        else:
            self._gauges["active_sessions"] = max(0, self._gauges.get("active_sessions", 0) - 1)

    @contextmanager
    def measure_latency(self, metric_type: str = "request"):
        """
        Context manager to measure operation latency.

        Example:
            with metrics.measure_latency("tool_call") as measurement:
                result = tool.run(...)
            # measurement.latency_ms is automatically recorded
        """
        measurement = _LatencyMeasurement()
        yield measurement
        measurement.stop()

    def get_stats(self) -> Dict[str, Any]:
        """Get current metrics statistics (for debugging/testing)."""
        stats = {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
        }

        # Calculate histogram stats
        for name, values in self._histograms.items():
            if values:
                stats[f"histogram.{name}"] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                }

        return stats

    def reset(self):
        """Reset all metrics (for testing)."""
        self._counters.clear()
        self._histograms.clear()
        self._gauges.clear()


class _LatencyMeasurement:
    """Helper class for measuring latency."""

    def __init__(self):
        self.start_time = time.perf_counter()
        self.latency_ms: Optional[float] = None

    def stop(self):
        """Stop the measurement and calculate latency."""
        self.latency_ms = (time.perf_counter() - self.start_time) * 1000
