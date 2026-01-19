# Observability Guide

OpenTelemetry-based tracing and metrics for the AI Assistant.

## Overview

The framework provides comprehensive observability through:

- **Distributed Tracing** — Track requests across components with OpenTelemetry
- **Metrics Collection** — Request latency, tool calls, errors, cache hits
- **Multiple Exporters** — Console, OTLP, Azure Monitor, Jaeger, Prometheus

## Configuration

### TOML Configuration

```toml
[agent.observability]
# Tracing
tracing_enabled = true
tracing_exporter = "otlp"  # "console", "otlp", "azure", "jaeger"

# Metrics
metrics_enabled = true
metrics_exporter = "prometheus"  # "console", "prometheus", "azure", "otlp"

# Service identification
service_name = "ai-assistant"
service_version = "1.0.0"
environment = "production"
```

### Environment Variables

```bash
# Azure Monitor
export APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=..."

# OTLP Collector
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
```

## Tracing

### Setup

```python
from src.observability import setup_tracing, TracingConfig

config = TracingConfig(
    enabled=True,
    service_name="ai-assistant",
    exporter_type="otlp",  # or "console", "azure", "jaeger"
    otlp_endpoint="http://localhost:4317",
    sample_rate=1.0,  # 100% sampling
    environment="production",
)

setup_tracing(config)
```

### Exporter Options

| Exporter | Use Case | Required Package |
|----------|----------|------------------|
| `console` | Development/debugging | (built-in) |
| `otlp` | OpenTelemetry Collector | `opentelemetry-exporter-otlp` |
| `azure` | Azure Monitor | `azure-monitor-opentelemetry-exporter` |
| `jaeger` | Jaeger backend | `opentelemetry-exporter-jaeger` |

### Decorators

Trace async functions:

```python
from src.observability import trace_async

@trace_async("process_data", {"component": "processor"})
async def process_data(data: str) -> str:
    # Automatically creates a span with:
    # - Name: "process_data"
    # - Attributes: component=processor, arg.data=...
    # - Success/failure status
    return data.upper()
```

Trace sync functions:

```python
from src.observability import trace_sync

@trace_sync("calculate", {"type": "math"})
def calculate(x: int, y: int) -> int:
    return x + y
```

### Context Managers

Trace LLM calls:

```python
from src.observability.tracing import trace_llm_call

with trace_llm_call("gpt-4o", prompt_tokens=100) as span:
    result = await llm.complete(prompt)
    span.set_attribute("completion_tokens", result.usage.completion_tokens)
```

Trace tool execution:

```python
from src.observability.tracing import trace_tool_execution

with trace_tool_execution("weather_lookup") as span:
    result = await tool.run({"location": "NYC"})
    span.set_attribute("result_length", len(result))
```

Trace workflow steps:

```python
from src.observability.tracing import trace_workflow_step

with trace_workflow_step("content-pipeline", "Researcher", step_index=0):
    result = await researcher_agent.run(message)
```

Trace cache operations:

```python
from src.observability.tracing import trace_cache_operation

with trace_cache_operation("get", "redis") as span:
    result = await cache.get(key)
    span.set_attribute("cache.hit", result is not None)
```

### Automatic Spans

The framework automatically creates spans for:

| Span Name | Attributes | Component |
|-----------|------------|-----------|
| `process_question` | chat_id, question_length | AIAssistant |
| `agent_run` | question_length, response_length | ChatAgent |
| `tool_execution` | tool.name | Tool calls |
| `llm_call` | llm.model, llm.provider, tokens | LLM requests |
| `cache_operation` | cache.operation, cache.type | Redis/Memory |

## Metrics

### Setup

```python
from src.observability import setup_metrics
from src.observability.metrics import MetricsConfig

config = MetricsConfig(
    enabled=True,
    exporter_type="prometheus",  # or "console", "azure", "otlp"
    prometheus_port=8000,
    service_name="ai-assistant",
    collection_interval=60,  # seconds
)

collector = setup_metrics(config)
```

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `ai_assistant.requests` | Counter | Total requests processed |
| `ai_assistant.request_latency` | Histogram | Request processing latency (ms) |
| `ai_assistant.tool_calls` | Counter | Total tool invocations |
| `ai_assistant.tool_latency` | Histogram | Tool execution latency (ms) |
| `ai_assistant.errors` | Counter | Total errors by type |
| `ai_assistant.cache_hits` | Counter | Cache hit count |
| `ai_assistant.cache_misses` | Counter | Cache miss count |
| `ai_assistant.tokens` | Counter | Token usage (prompt/completion) |
| `ai_assistant.active_sessions` | UpDownCounter | Active session count |

### Recording Metrics

```python
from src.observability import get_metrics

metrics = get_metrics()

# Record a request
metrics.record_request(
    latency_ms=150.5,
    success=True,
    chat_id="abc123",
    workflow="content-pipeline"  # optional
)

# Record a tool call
metrics.record_tool_call(
    tool_name="weather_lookup",
    latency_ms=45.2,
    success=True
)

# Record an error
metrics.record_error(
    error_type="ValidationError",
    component="input_validator"
)

# Record cache access
metrics.record_cache_access(hit=True, cache_type="redis")

# Record token usage
metrics.record_tokens(
    prompt_tokens=100,
    completion_tokens=250,
    model="gpt-4o"
)

# Track sessions
metrics.record_session_start()
metrics.record_session_end()
```

### Latency Measurement

```python
from src.observability import get_metrics

metrics = get_metrics()

with metrics.measure_latency("tool_call") as measurement:
    result = await tool.run(args)
# measurement.latency_ms is automatically recorded
```

### Prometheus Endpoint

When using the Prometheus exporter, metrics are available at:

```
http://localhost:8000/metrics
```

Example output:

```
# HELP ai_assistant_requests_total Total number of requests processed
# TYPE ai_assistant_requests_total counter
ai_assistant_requests_total{success="true",type="question"} 150

# HELP ai_assistant_request_latency_milliseconds Request processing latency
# TYPE ai_assistant_request_latency_milliseconds histogram
ai_assistant_request_latency_milliseconds_bucket{le="100"} 50
ai_assistant_request_latency_milliseconds_bucket{le="500"} 140
```

## Integration with AIAssistant

Observability is automatically initialized when configured:

```toml
[agent.observability]
tracing_enabled = true
metrics_enabled = true
service_name = "my-agent"
tracing_exporter = "azure"
metrics_exporter = "prometheus"
```

The AIAssistant automatically:

1. Creates spans for `process_question` and `process_question_stream`
2. Records request latency and success metrics
3. Records tool call metrics via middleware
4. Records cache hit/miss metrics
5. Propagates trace context through the request pipeline

## Azure Monitor Integration

### Setup

1. Install the Azure Monitor exporter:

```bash
pip install azure-monitor-opentelemetry-exporter
```

2. Configure the connection string:

```toml
[agent.observability]
tracing_enabled = true
tracing_exporter = "azure"
metrics_enabled = true
metrics_exporter = "azure"
```

```bash
export APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=xxx;IngestionEndpoint=https://..."
```

Or in TracingConfig:

```python
config = TracingConfig(
    enabled=True,
    exporter_type="azure",
    azure_connection_string="InstrumentationKey=xxx;..."
)
```

### Viewing in Azure Portal

1. Navigate to your Application Insights resource
2. **Transaction search** — View individual traces
3. **Application map** — See service dependencies
4. **Metrics** — View custom metrics dashboards
5. **Failures** — Analyze errors and exceptions

## Debugging

### Get Metrics Statistics

```python
from src.observability import get_metrics

metrics = get_metrics()
stats = metrics.get_stats()

print(stats)
# {
#   "counters": {"requests.question.true": 150, ...},
#   "gauges": {"active_sessions": 5},
#   "histogram.request_latency": {"count": 150, "min": 45, "max": 1200, "avg": 250}
# }
```

### Reset Metrics (Testing)

```python
metrics.reset()
```

## Installation

Core packages:

```bash
pip install opentelemetry-api opentelemetry-sdk
```

Exporters (as needed):

```bash
# OTLP (OpenTelemetry Collector)
pip install opentelemetry-exporter-otlp

# Azure Monitor
pip install azure-monitor-opentelemetry-exporter

# Jaeger
pip install opentelemetry-exporter-jaeger

# Prometheus
pip install opentelemetry-exporter-prometheus
```
