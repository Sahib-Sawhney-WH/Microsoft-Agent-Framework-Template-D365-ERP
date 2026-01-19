# Docker Deployment

This guide covers deploying the MSFT Agent Framework using Docker containers.

## Overview

Docker deployment is ideal for:
- Local development and testing
- Small-scale deployments
- CI/CD pipeline testing
- Quick proof-of-concept deployments

## Prerequisites

- Docker 20.10+ installed
- Access to Azure OpenAI resource
- Azure credentials configured

## Building the Docker Image

### Using the Provided Dockerfile

The project includes a multi-stage Dockerfile optimized for production:

```bash
cd deployment
docker build -t msft-agent-framework:latest -f Dockerfile ..
```

### Understanding the Multi-Stage Build

The Dockerfile uses a multi-stage build for smaller, more secure images:

```dockerfile
# Stage 1: Builder - installs dependencies
FROM python:3.12-slim as builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc
COPY pyproject.toml .
RUN pip install --user --no-cache-dir .

# Stage 2: Runtime - minimal production image
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY src/ ./src/
COPY config/ ./config/
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "-m", "src.orchestrator.main"]
```

**Benefits:**
- Smaller final image (no build tools)
- Reduced attack surface
- Faster deployments

### Build Arguments

Customize the build with arguments:

```bash
docker build \
  --build-arg PYTHON_VERSION=3.11 \
  -t msft-agent-framework:latest \
  -f deployment/Dockerfile .
```

## Running the Container

### Basic Run

```bash
docker run -d \
  --name msft-agent \
  -p 8000:8000 \
  -e AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" \
  -e AZURE_OPENAI_DEPLOYMENT="gpt-4o" \
  -e AZURE_TENANT_ID="your-tenant-id" \
  -e AZURE_CLIENT_ID="your-client-id" \
  -e AZURE_CLIENT_SECRET="your-client-secret" \
  msft-agent-framework:latest
```

### With Configuration File

Mount your custom configuration:

```bash
docker run -d \
  --name msft-agent \
  -p 8000:8000 \
  -v $(pwd)/config/agent.toml:/app/config/agent.toml:ro \
  -e AZURE_TENANT_ID="your-tenant-id" \
  -e AZURE_CLIENT_ID="your-client-id" \
  -e AZURE_CLIENT_SECRET="your-client-secret" \
  msft-agent-framework:latest
```

### Environment Variables from File

For production, use an environment file:

```bash
# Create .env file
cat > .env << EOF
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
LOG_LEVEL=INFO
EOF

# Run with env file
docker run -d \
  --name msft-agent \
  -p 8000:8000 \
  --env-file .env \
  msft-agent-framework:latest
```

**Important:** Never commit `.env` files to version control.

## Docker Compose

For development environments with Redis and storage emulator:

### docker-compose.yml

```yaml
version: '3.8'

services:
  agent:
    build:
      context: ..
      dockerfile: deployment/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
      - AZURE_OPENAI_DEPLOYMENT=${AZURE_OPENAI_DEPLOYMENT}
      - AZURE_TENANT_ID=${AZURE_TENANT_ID}
      - AZURE_CLIENT_ID=${AZURE_CLIENT_ID}
      - AZURE_CLIENT_SECRET=${AZURE_CLIENT_SECRET}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_SSL=false
    volumes:
      - ../config/agent.toml:/app/config/agent.toml:ro
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  # Azure Storage Emulator (Azurite) for local development
  azurite:
    image: mcr.microsoft.com/azure-storage/azurite
    ports:
      - "10000:10000"  # Blob
      - "10001:10001"  # Queue
      - "10002:10002"  # Table
    volumes:
      - azurite-data:/data
    command: azurite --blobHost 0.0.0.0 --queueHost 0.0.0.0 --tableHost 0.0.0.0

volumes:
  redis-data:
  azurite-data:
```

### Running with Docker Compose

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f agent

# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v
```

## Health Checks

### Docker Health Check

The container exposes health endpoints:

```bash
# Check liveness
curl http://localhost:8000/health/live

# Check readiness
curl http://localhost:8000/health/ready

# Full health status
curl http://localhost:8000/health
```

### Docker Health Check Configuration

Add health checks to your container:

```bash
docker run -d \
  --name msft-agent \
  --health-cmd="curl -f http://localhost:8000/health/live || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  --health-start-period=10s \
  msft-agent-framework:latest
```

### Checking Container Health

```bash
# View health status
docker inspect --format='{{.State.Health.Status}}' msft-agent

# View health check logs
docker inspect --format='{{json .State.Health}}' msft-agent | jq
```

## Logging

### View Logs

```bash
# Follow logs
docker logs -f msft-agent

# Last 100 lines
docker logs --tail 100 msft-agent

# With timestamps
docker logs -t msft-agent
```

### Log Configuration

Configure logging level via environment:

```bash
docker run -d \
  -e LOG_LEVEL=DEBUG \
  msft-agent-framework:latest
```

### JSON Logging for Production

The framework uses `structlog` which outputs JSON logs by default:

```json
{"event": "Processing question", "chat_id": "abc123", "timestamp": "2024-01-15T10:30:00Z", "level": "info"}
```

Collect these logs with your preferred log aggregator (ELK, Splunk, etc.).

## Networking

### Exposing Ports

```bash
# Single port
docker run -p 8000:8000 msft-agent-framework:latest

# Multiple ports (if API + metrics)
docker run -p 8000:8000 -p 9090:9090 msft-agent-framework:latest

# Bind to specific interface
docker run -p 127.0.0.1:8000:8000 msft-agent-framework:latest
```

### Custom Networks

```bash
# Create network
docker network create agent-network

# Run with network
docker run -d \
  --name msft-agent \
  --network agent-network \
  msft-agent-framework:latest
```

## Resource Limits

Set resource constraints for production:

```bash
docker run -d \
  --name msft-agent \
  --memory=2g \
  --cpus=2.0 \
  --memory-swap=2g \
  msft-agent-framework:latest
```

### Recommended Resources

| Workload | Memory | CPU |
|----------|--------|-----|
| Development | 512MB | 0.5 |
| Light Production | 1GB | 1.0 |
| Standard Production | 2GB | 2.0 |
| High Throughput | 4GB+ | 4.0+ |

## Debugging

### Interactive Shell

```bash
# Start shell in running container
docker exec -it msft-agent /bin/bash

# Start new container with shell
docker run -it --entrypoint /bin/bash msft-agent-framework:latest
```

### Debug Mode

```bash
docker run -it \
  -e LOG_LEVEL=DEBUG \
  -e PYTHONDONTWRITEBYTECODE=0 \
  msft-agent-framework:latest
```

## Image Management

### Tagging

```bash
# Tag with version
docker tag msft-agent-framework:latest msft-agent-framework:1.0.0

# Tag for registry
docker tag msft-agent-framework:latest myregistry.azurecr.io/msft-agent-framework:latest
```

### Push to Registry

```bash
# Azure Container Registry
az acr login --name myregistry
docker push myregistry.azurecr.io/msft-agent-framework:latest

# Docker Hub
docker login
docker push myorg/msft-agent-framework:latest
```

### Cleanup

```bash
# Remove container
docker rm -f msft-agent

# Remove image
docker rmi msft-agent-framework:latest

# Prune unused images
docker image prune -a
```

## Production Considerations

### Security

1. **Run as non-root user** (add to Dockerfile):
   ```dockerfile
   RUN useradd -m -u 1000 agent
   USER agent
   ```

2. **Read-only filesystem**:
   ```bash
   docker run --read-only --tmpfs /tmp msft-agent-framework:latest
   ```

3. **No new privileges**:
   ```bash
   docker run --security-opt=no-new-privileges msft-agent-framework:latest
   ```

### High Availability

For HA, consider:
- Running multiple containers behind a load balancer
- Using Docker Swarm or Kubernetes
- See [Kubernetes Deployment](kubernetes.md) for orchestration

### Monitoring

Integrate with monitoring:

```bash
docker run -d \
  -e OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317" \
  -e OTEL_SERVICE_NAME="msft-agent" \
  msft-agent-framework:latest
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker logs msft-agent

# Check exit code
docker inspect msft-agent --format='{{.State.ExitCode}}'
```

### Connection Issues

```bash
# Check network connectivity
docker exec msft-agent curl -v https://your-resource.openai.azure.com/

# DNS resolution
docker exec msft-agent nslookup your-resource.openai.azure.com
```

### Out of Memory

```bash
# Check memory usage
docker stats msft-agent

# Increase memory limit
docker update --memory=4g msft-agent
```

## Related Documentation

- [Deployment Overview](overview.md) — Compare deployment options
- [Kubernetes Deployment](kubernetes.md) — Production orchestration
- [Azure Deployment](azure-deployment.md) — Azure PaaS options
- [Production Checklist](production-checklist.md) — Pre-deployment verification

---
*Last updated: 2026-01-17*
