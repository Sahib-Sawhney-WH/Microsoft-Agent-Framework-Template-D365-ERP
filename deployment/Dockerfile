# Multi-stage build for MSFT Agent Framework
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and install Python dependencies
COPY pyproject.toml .
RUN pip install --user --no-cache-dir .

# Final stage
FROM python:3.12-slim

# Security labels
LABEL org.opencontainers.image.title="MSFT Agent Framework"
LABEL org.opencontainers.image.description="AI Assistant with Microsoft Agent Framework"
LABEL org.opencontainers.image.vendor="RSM"
LABEL org.opencontainers.image.licenses="MIT"
LABEL security.privileged="false"

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security (CIS Docker Benchmark 4.1)
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Copy Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Set PATH to use pip packages from builder
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Disable Python hash randomization for reproducibility
    PYTHONHASHSEED=0

# Copy application code with proper ownership
COPY --chown=appuser:appgroup src/ ./src/
COPY --chown=appuser:appgroup config/ ./config/
COPY --chown=appuser:appgroup pyproject.toml .

# Switch to non-root user
USER appuser

# Health check endpoint (configure endpoint in your application)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose default port (adjust as needed)
EXPOSE 8000

# Set default command (override as needed)
CMD ["python", "-m", "src.orchestrator.main"]
