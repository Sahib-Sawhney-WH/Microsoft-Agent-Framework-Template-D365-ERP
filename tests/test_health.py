"""
Tests for the health check module.

Tests health checker functionality for Kubernetes probes.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_health_status_values(self):
        """Test health status enum values."""
        from src.health import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"


class TestComponentCheck:
    """Tests for ComponentCheck dataclass."""

    def test_component_check_creation(self):
        """Test creating a component check result."""
        from src.health import ComponentCheck, HealthStatus

        check = ComponentCheck(
            name="test_component",
            status=HealthStatus.HEALTHY,
            latency_ms=10.5,
            message="Component is healthy"
        )

        assert check.name == "test_component"
        assert check.status == HealthStatus.HEALTHY
        assert check.latency_ms == 10.5
        assert check.message == "Component is healthy"

    def test_component_check_with_details(self):
        """Test component check with details."""
        from src.health import ComponentCheck, HealthStatus

        check = ComponentCheck(
            name="redis",
            status=HealthStatus.HEALTHY,
            latency_ms=5.0,
            details={"connections": 10, "memory_mb": 100}
        )

        assert check.details["connections"] == 10


class TestHealthCheckConfig:
    """Tests for HealthCheckConfig."""

    def test_default_config(self):
        """Test default health check configuration."""
        from src.health import HealthCheckConfig

        config = HealthCheckConfig()
        assert config.enabled is True
        assert config.timeout_seconds == 5.0
        assert config.cache_seconds == 10.0
        assert config.include_details is True

    def test_custom_config(self):
        """Test custom health check configuration."""
        from src.health import HealthCheckConfig

        config = HealthCheckConfig(
            timeout_seconds=10.0,
            cache_seconds=30.0,
            version="2.0.0"
        )

        assert config.timeout_seconds == 10.0
        assert config.cache_seconds == 30.0
        assert config.version == "2.0.0"


class TestHealthChecker:
    """Tests for HealthChecker."""

    def test_health_checker_initialization(self):
        """Test health checker initialization."""
        from src.health import HealthChecker

        checker = HealthChecker()
        assert checker is not None

    def test_register_check(self):
        """Test registering a health check."""
        from src.health import HealthChecker, ComponentCheck, HealthStatus

        checker = HealthChecker()

        async def mock_check():
            return ComponentCheck(
                name="mock",
                status=HealthStatus.HEALTHY,
                latency_ms=1.0
            )

        checker.register_check("mock", mock_check)
        assert "mock" in checker._checks

    @pytest.mark.asyncio
    async def test_check_all_no_checks(self):
        """Test check_all with no registered checks."""
        from src.health import HealthChecker, HealthStatus

        checker = HealthChecker()
        result = await checker.check_all()

        assert result.status == HealthStatus.HEALTHY
        assert len(result.components) == 0

    @pytest.mark.asyncio
    async def test_check_all_healthy(self):
        """Test check_all with all healthy components."""
        from src.health import HealthChecker, ComponentCheck, HealthStatus

        checker = HealthChecker()

        async def healthy_check():
            return ComponentCheck(
                name="component1",
                status=HealthStatus.HEALTHY,
                latency_ms=5.0
            )

        checker.register_check("component1", healthy_check)
        result = await checker.check_all()

        assert result.status == HealthStatus.HEALTHY
        assert len(result.components) == 1

    @pytest.mark.asyncio
    async def test_check_all_degraded(self):
        """Test check_all with degraded component."""
        from src.health import HealthChecker, ComponentCheck, HealthStatus

        checker = HealthChecker()

        async def degraded_check():
            return ComponentCheck(
                name="degraded",
                status=HealthStatus.DEGRADED,
                latency_ms=100.0,
                message="High latency"
            )

        checker.register_check("degraded", degraded_check)
        result = await checker.check_all()

        assert result.status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_check_all_unhealthy(self):
        """Test check_all with unhealthy component."""
        from src.health import HealthChecker, ComponentCheck, HealthStatus

        checker = HealthChecker()

        async def healthy_check():
            return ComponentCheck(
                name="healthy",
                status=HealthStatus.HEALTHY,
                latency_ms=5.0
            )

        async def unhealthy_check():
            return ComponentCheck(
                name="unhealthy",
                status=HealthStatus.UNHEALTHY,
                latency_ms=0,
                message="Connection failed"
            )

        checker.register_check("healthy", healthy_check)
        checker.register_check("unhealthy", unhealthy_check)
        result = await checker.check_all()

        # Unhealthy takes precedence
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_all_with_timeout(self):
        """Test check_all handles timeouts."""
        import asyncio
        from src.health import HealthChecker, HealthCheckConfig, HealthStatus

        config = HealthCheckConfig(timeout_seconds=0.1)
        checker = HealthChecker(config)

        async def slow_check():
            await asyncio.sleep(1.0)  # Longer than timeout
            return ComponentCheck(
                name="slow",
                status=HealthStatus.HEALTHY,
                latency_ms=1000.0
            )

        checker.register_check("slow", slow_check)
        result = await checker.check_all()

        # Should timeout and be unhealthy
        assert result.status == HealthStatus.UNHEALTHY
        assert result.components[0].message == "Health check timed out"

    @pytest.mark.asyncio
    async def test_check_readiness(self):
        """Test readiness check."""
        from src.health import HealthChecker, ComponentCheck, HealthStatus

        checker = HealthChecker()

        async def healthy_check():
            return ComponentCheck(
                name="main",
                status=HealthStatus.HEALTHY,
                latency_ms=5.0
            )

        checker.register_check("main", healthy_check)

        is_ready = await checker.check_readiness()
        assert is_ready is True

    @pytest.mark.asyncio
    async def test_check_liveness(self):
        """Test liveness check."""
        from src.health import HealthChecker

        checker = HealthChecker()

        # Liveness should always return True (service is running)
        is_alive = await checker.check_liveness()
        assert is_alive is True

    @pytest.mark.asyncio
    async def test_result_caching(self):
        """Test that results are cached."""
        from src.health import HealthChecker, HealthCheckConfig, ComponentCheck, HealthStatus

        config = HealthCheckConfig(cache_seconds=60.0)
        checker = HealthChecker(config)

        call_count = 0

        async def counting_check():
            nonlocal call_count
            call_count += 1
            return ComponentCheck(
                name="counter",
                status=HealthStatus.HEALTHY,
                latency_ms=1.0
            )

        checker.register_check("counter", counting_check)

        # First call
        await checker.check_all()
        assert call_count == 1

        # Second call should use cache
        await checker.check_all()
        assert call_count == 1

    def test_to_dict(self):
        """Test converting result to dictionary."""
        from src.health import HealthChecker, HealthCheckResult, ComponentCheck, HealthStatus

        checker = HealthChecker()
        result = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            timestamp=datetime.now(timezone.utc),
            version="1.0.0",
            components=[
                ComponentCheck(
                    name="test",
                    status=HealthStatus.HEALTHY,
                    latency_ms=5.0
                )
            ],
            uptime_seconds=3600.0
        )

        result_dict = checker.to_dict(result)

        assert result_dict["status"] == "healthy"
        assert "timestamp" in result_dict
        assert result_dict["version"] == "1.0.0"
        assert len(result_dict["components"]) == 1


class TestHealthCheckFactories:
    """Tests for health check factory functions."""

    @pytest.mark.asyncio
    async def test_create_redis_check(self):
        """Test Redis health check factory."""
        from src.health import create_redis_check, HealthStatus

        mock_cache = MagicMock()
        mock_cache._client = None

        check_fn = await create_redis_check(mock_cache)
        result = await check_fn()

        # Without client, should be degraded
        assert result.status == HealthStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_create_mcp_check(self):
        """Test MCP health check factory."""
        from src.health import create_mcp_check, HealthStatus

        mock_manager = MagicMock()
        mock_manager.tools = ["tool1", "tool2", "tool3"]

        check_fn = await create_mcp_check(mock_manager)
        result = await check_fn()

        assert result.status == HealthStatus.HEALTHY
        assert result.details["tool_count"] == 3

    @pytest.mark.asyncio
    async def test_create_mcp_check_no_tools(self):
        """Test MCP health check with no tools."""
        from src.health import create_mcp_check, HealthStatus

        mock_manager = MagicMock()
        mock_manager.tools = []

        check_fn = await create_mcp_check(mock_manager)
        result = await check_fn()

        assert result.status == HealthStatus.HEALTHY
        assert "No MCP servers" in result.message
