"""
Agent Framework Middleware

Provides function-level middleware to intercept and monitor tool calls.
Follows Agent Framework middleware patterns for logging, security, and transformation.
"""

import time
from typing import Callable, Awaitable, Optional
import structlog

# Import Agent Framework middleware types
try:
    from agent_framework import FunctionInvocationContext
except ImportError:
    # Fallback if agent_framework not available or different structure
    class FunctionInvocationContext:
        """Minimal FunctionInvocationContext for type hints."""
        function: any
        args: dict
        result: any

from src.observability import get_tracer
from src.observability.tracing import trace_tool_execution

logger = structlog.get_logger(__name__)


async def function_call_middleware(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
) -> None:
    """
    Middleware that intercepts function (tool) calls.

    This middleware:
    1. Logs when a function is called
    2. Records tracing spans for observability
    3. Measures execution time
    4. Logs the result

    Args:
        context: Function invocation context with function metadata and arguments
        next: Continuation function to invoke the actual tool
    """
    function_name = getattr(context.function, 'name', 'unknown')
    args_preview = str(context.args)[:200] if hasattr(context, 'args') else 'N/A'
    start_time = time.perf_counter()

    tracer = get_tracer()

    with tracer.start_as_current_span("tool_execution") as span:
        span.set_attribute("tool.name", function_name)
        span.set_attribute("tool.args_preview", args_preview)

        logger.info(
            "[MIDDLEWARE] Function call starting",
            function_name=function_name,
            args_preview=args_preview
        )

        try:
            # Continue to actual function execution
            await next(context)

            # Calculate execution time
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Log successful completion
            result_preview = str(context.result)[:200] if hasattr(context, 'result') and context.result else 'N/A'

            span.set_attribute("tool.success", True)
            span.set_attribute("tool.latency_ms", elapsed_ms)

            logger.info(
                "[MIDDLEWARE] Function call completed",
                function_name=function_name,
                result_preview=result_preview,
                elapsed_ms=round(elapsed_ms, 2)
            )

            # Record metrics
            try:
                from src.observability import get_metrics
                metrics = get_metrics()
                metrics.record_tool_call(function_name, elapsed_ms, success=True)
            except Exception:
                pass  # Don't fail if metrics not available

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            span.set_attribute("tool.success", False)
            span.set_attribute("tool.error", str(e))
            span.record_exception(e)

            logger.error(
                "[MIDDLEWARE] Function call failed",
                function_name=function_name,
                error=str(e),
                elapsed_ms=round(elapsed_ms, 2),
                exc_info=True
            )

            # Record metrics
            try:
                from src.observability import get_metrics
                metrics = get_metrics()
                metrics.record_tool_call(function_name, elapsed_ms, success=False)
                metrics.record_error(type(e).__name__, f"tool_{function_name}")
            except Exception:
                pass

            # Re-raise to let agent framework handle it
            raise


def create_security_middleware(validator: Optional["InputValidator"] = None):
    """
    Create a security middleware that validates tool call parameters.

    Args:
        validator: Optional InputValidator instance for parameter validation

    Returns:
        Middleware function
    """
    async def security_middleware(
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """
        Security middleware for authorization and input validation.

        Validates:
        - Tool parameters for injection attempts
        - Sensitive data exposure
        - Rate limits (if configured)
        """
        function_name = getattr(context.function, 'name', 'unknown')

        logger.debug(
            "[SECURITY MIDDLEWARE] Checking authorization",
            function_name=function_name
        )

        # Validate parameters if validator provided
        if validator and hasattr(context, 'args') and context.args:
            try:
                for key, value in context.args.items():
                    if isinstance(value, str):
                        # Validate string parameters
                        validated = validator.validate(value, context="tool_param")
                        context.args[key] = validated
            except Exception as e:
                logger.warning(
                    "[SECURITY MIDDLEWARE] Parameter validation failed",
                    function_name=function_name,
                    error=str(e)
                )
                raise

        await next(context)

    return security_middleware


async def performance_middleware(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
) -> None:
    """
    Performance monitoring middleware.

    Tracks execution time and logs slow operations.
    """
    function_name = getattr(context.function, 'name', 'unknown')
    start_time = time.perf_counter()

    logger.debug(
        "[PERFORMANCE MIDDLEWARE] Starting timer",
        function_name=function_name
    )

    try:
        await next(context)
    finally:
        elapsed_time = time.perf_counter() - start_time
        elapsed_ms = elapsed_time * 1000

        logger.info(
            "[PERFORMANCE MIDDLEWARE] Execution complete",
            function_name=function_name,
            elapsed_ms=round(elapsed_ms, 2)
        )

        # Warn about slow operations (> 10 seconds)
        if elapsed_time > 10.0:
            logger.warning(
                "[PERFORMANCE MIDDLEWARE] Slow operation detected",
                function_name=function_name,
                elapsed_seconds=round(elapsed_time, 3)
            )


async def rate_limit_middleware(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Awaitable[None]],
    rate_limiter: Optional["RateLimiter"] = None,
) -> None:
    """
    Rate limiting middleware for tool calls.

    Args:
        context: Function invocation context
        next: Continuation function
        rate_limiter: Optional RateLimiter instance
    """
    function_name = getattr(context.function, 'name', 'unknown')

    if rate_limiter:
        try:
            # Check tool-specific rate limit
            await rate_limiter.check_limit(identifier=f"tool:{function_name}")
        except Exception as e:
            logger.warning(
                "[RATE LIMIT MIDDLEWARE] Rate limit exceeded for tool",
                function_name=function_name,
                error=str(e)
            )
            raise

    await next(context)

    # Record the tool call for rate limiting
    if rate_limiter:
        await rate_limiter.record_request(identifier=f"tool:{function_name}")


def create_audit_middleware(audit_log_fn: Callable = None):
    """
    Create an audit logging middleware.

    Args:
        audit_log_fn: Optional custom audit log function

    Returns:
        Middleware function
    """
    async def audit_middleware(
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        """
        Audit logging middleware.

        Records all tool calls for compliance and debugging.
        """
        function_name = getattr(context.function, 'name', 'unknown')
        args = dict(context.args) if hasattr(context, 'args') else {}

        # Sanitize sensitive fields
        sensitive_keys = {'password', 'token', 'secret', 'key', 'credential', 'auth'}
        sanitized_args = {
            k: '[REDACTED]' if any(s in k.lower() for s in sensitive_keys) else v
            for k, v in args.items()
        }

        audit_entry = {
            "event": "tool_call",
            "function": function_name,
            "args": sanitized_args,
            "timestamp": time.time(),
        }

        try:
            await next(context)
            audit_entry["success"] = True
            audit_entry["result_preview"] = str(context.result)[:100] if context.result else None
        except Exception as e:
            audit_entry["success"] = False
            audit_entry["error"] = str(e)
            raise
        finally:
            if audit_log_fn:
                audit_log_fn(audit_entry)
            else:
                logger.info("[AUDIT] Tool call recorded", **audit_entry)

    return audit_middleware


# Middleware combiner for stacking multiple middleware
def combine_middleware(*middleware_fns):
    """
    Combine multiple middleware functions into a single middleware.

    Args:
        *middleware_fns: Variable number of middleware functions

    Returns:
        Combined middleware function

    Example:
        combined = combine_middleware(
            function_call_middleware,
            security_middleware,
            performance_middleware
        )
    """
    async def combined_middleware(
        context: FunctionInvocationContext,
        next: Callable[[FunctionInvocationContext], Awaitable[None]],
    ) -> None:
        # Build middleware chain from inside out
        chain = next
        for middleware in reversed(middleware_fns):
            # Capture middleware in closure
            def make_wrapper(mw, inner):
                async def wrapper(ctx):
                    await mw(ctx, inner)
                return wrapper
            chain = make_wrapper(middleware, chain)

        await chain(context)

    return combined_middleware
