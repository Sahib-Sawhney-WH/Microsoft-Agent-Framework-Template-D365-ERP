"""
Rate Limiting for the AI Assistant.

Provides token bucket and sliding window rate limiting
to protect against abuse and ensure fair usage.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from collections import defaultdict

import structlog

logger = structlog.get_logger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        limit_type: str,
        retry_after: Optional[float] = None
    ):
        super().__init__(message)
        self.limit_type = limit_type
        self.retry_after = retry_after


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    enabled: bool = True

    # Request limits
    requests_per_minute: int = 60
    requests_per_hour: int = 1000

    # Token limits
    tokens_per_minute: int = 100000
    tokens_per_hour: int = 1000000

    # Concurrent request limits
    max_concurrent_requests: int = 10

    # Per-user vs global
    per_user: bool = True  # If False, limits are global

    # Burst allowance (percentage over limit allowed in short bursts)
    burst_multiplier: float = 1.5


@dataclass
class RateLimitState:
    """State for a single rate limit window."""
    count: int = 0
    tokens: int = 0
    window_start: float = field(default_factory=time.time)
    concurrent: int = 0


class RateLimiter:
    """
    Rate limiter using sliding window algorithm.

    Supports:
    - Per-user and global rate limiting
    - Request count limits
    - Token usage limits
    - Concurrent request limits
    """

    def __init__(self, config: RateLimitConfig):
        """
        Initialize rate limiter.

        Args:
            config: RateLimitConfig with limit settings
        """
        self.config = config
        self._enabled = config.enabled

        # Per-user state
        self._user_minute_state: Dict[str, RateLimitState] = defaultdict(RateLimitState)
        self._user_hour_state: Dict[str, RateLimitState] = defaultdict(RateLimitState)

        # Global state
        self._global_minute_state = RateLimitState()
        self._global_hour_state = RateLimitState()

        # Concurrent request tracking
        self._concurrent_requests: Dict[str, int] = defaultdict(int)
        self._global_concurrent = 0

        # Lock for thread safety
        self._lock = asyncio.Lock()

        logger.info(
            "Rate limiter initialized",
            enabled=config.enabled,
            requests_per_minute=config.requests_per_minute,
            tokens_per_minute=config.tokens_per_minute
        )

    async def check_limit(
        self,
        user_id: Optional[str] = None,
        estimated_tokens: int = 0
    ) -> bool:
        """
        Check if a request is within rate limits.

        Args:
            user_id: Optional user identifier for per-user limits
            estimated_tokens: Estimated tokens for this request

        Returns:
            True if within limits

        Raises:
            RateLimitExceeded: If any limit is exceeded
        """
        if not self._enabled:
            return True

        async with self._lock:
            now = time.time()
            identifier = user_id or "global"

            # Clean up old windows
            self._cleanup_windows(now)

            # Check concurrent limit
            await self._check_concurrent_limit(identifier)

            # Check request limits
            await self._check_request_limit(identifier, now)

            # Check token limits
            if estimated_tokens > 0:
                await self._check_token_limit(identifier, estimated_tokens, now)

            return True

    async def _check_concurrent_limit(self, identifier: str) -> None:
        """Check concurrent request limit."""
        current = self._concurrent_requests[identifier] if self.config.per_user else self._global_concurrent

        if current >= self.config.max_concurrent_requests:
            logger.warning(
                "Concurrent request limit exceeded",
                identifier=identifier,
                current=current,
                limit=self.config.max_concurrent_requests
            )
            raise RateLimitExceeded(
                f"Too many concurrent requests: {current}/{self.config.max_concurrent_requests}",
                limit_type="concurrent",
                retry_after=1.0
            )

    async def _check_request_limit(self, identifier: str, now: float) -> None:
        """Check request count limits."""
        # Per-minute limit
        minute_state = self._user_minute_state[identifier] if self.config.per_user else self._global_minute_state

        if now - minute_state.window_start >= 60:
            minute_state.count = 0
            minute_state.window_start = now

        max_requests = int(self.config.requests_per_minute * self.config.burst_multiplier)
        if minute_state.count >= max_requests:
            retry_after = 60 - (now - minute_state.window_start)
            logger.warning(
                "Request rate limit exceeded (per minute)",
                identifier=identifier,
                count=minute_state.count,
                limit=self.config.requests_per_minute
            )
            raise RateLimitExceeded(
                f"Rate limit exceeded: {minute_state.count}/{self.config.requests_per_minute} requests per minute",
                limit_type="requests_per_minute",
                retry_after=max(0, retry_after)
            )

        # Per-hour limit
        hour_state = self._user_hour_state[identifier] if self.config.per_user else self._global_hour_state

        if now - hour_state.window_start >= 3600:
            hour_state.count = 0
            hour_state.window_start = now

        if hour_state.count >= self.config.requests_per_hour:
            retry_after = 3600 - (now - hour_state.window_start)
            logger.warning(
                "Request rate limit exceeded (per hour)",
                identifier=identifier,
                count=hour_state.count,
                limit=self.config.requests_per_hour
            )
            raise RateLimitExceeded(
                f"Rate limit exceeded: {hour_state.count}/{self.config.requests_per_hour} requests per hour",
                limit_type="requests_per_hour",
                retry_after=max(0, retry_after)
            )

    async def _check_token_limit(
        self,
        identifier: str,
        tokens: int,
        now: float
    ) -> None:
        """Check token usage limits."""
        minute_state = self._user_minute_state[identifier] if self.config.per_user else self._global_minute_state

        max_tokens = int(self.config.tokens_per_minute * self.config.burst_multiplier)
        if minute_state.tokens + tokens > max_tokens:
            retry_after = 60 - (now - minute_state.window_start)
            logger.warning(
                "Token rate limit exceeded",
                identifier=identifier,
                current_tokens=minute_state.tokens,
                requested=tokens,
                limit=self.config.tokens_per_minute
            )
            raise RateLimitExceeded(
                f"Token limit exceeded: {minute_state.tokens + tokens}/{self.config.tokens_per_minute} tokens per minute",
                limit_type="tokens_per_minute",
                retry_after=max(0, retry_after)
            )

    async def record_request(
        self,
        user_id: Optional[str] = None,
        tokens_used: int = 0
    ) -> None:
        """
        Record a completed request for rate limiting.

        Args:
            user_id: Optional user identifier
            tokens_used: Actual tokens used
        """
        if not self._enabled:
            return

        async with self._lock:
            identifier = user_id or "global"

            # Update minute state
            minute_state = self._user_minute_state[identifier] if self.config.per_user else self._global_minute_state
            minute_state.count += 1
            minute_state.tokens += tokens_used

            # Update hour state
            hour_state = self._user_hour_state[identifier] if self.config.per_user else self._global_hour_state
            hour_state.count += 1
            hour_state.tokens += tokens_used

            logger.debug(
                "Recorded request",
                identifier=identifier,
                tokens=tokens_used,
                minute_count=minute_state.count,
                hour_count=hour_state.count
            )

    async def acquire_concurrent_slot(self, user_id: Optional[str] = None) -> None:
        """Acquire a concurrent request slot."""
        if not self._enabled:
            return

        async with self._lock:
            identifier = user_id or "global"
            if self.config.per_user:
                self._concurrent_requests[identifier] += 1
            else:
                self._global_concurrent += 1

    async def release_concurrent_slot(self, user_id: Optional[str] = None) -> None:
        """Release a concurrent request slot."""
        if not self._enabled:
            return

        async with self._lock:
            identifier = user_id or "global"
            if self.config.per_user:
                self._concurrent_requests[identifier] = max(0, self._concurrent_requests[identifier] - 1)
            else:
                self._global_concurrent = max(0, self._global_concurrent - 1)

    def _cleanup_windows(self, now: float) -> None:
        """Clean up expired rate limit windows."""
        # Clean up minute windows older than 2 minutes
        expired_minute = [
            k for k, v in self._user_minute_state.items()
            if now - v.window_start > 120
        ]
        for k in expired_minute:
            del self._user_minute_state[k]

        # Clean up hour windows older than 2 hours
        expired_hour = [
            k for k, v in self._user_hour_state.items()
            if now - v.window_start > 7200
        ]
        for k in expired_hour:
            del self._user_hour_state[k]

        # Clean up concurrent counters that are zero
        expired_concurrent = [
            k for k, v in self._concurrent_requests.items()
            if v == 0
        ]
        for k in expired_concurrent:
            del self._concurrent_requests[k]

    def get_usage(self, user_id: Optional[str] = None) -> Dict:
        """Get current usage statistics for a user."""
        identifier = user_id or "global"

        minute_state = self._user_minute_state.get(identifier, RateLimitState())
        hour_state = self._user_hour_state.get(identifier, RateLimitState())

        return {
            "requests_minute": {
                "used": minute_state.count,
                "limit": self.config.requests_per_minute,
                "remaining": max(0, self.config.requests_per_minute - minute_state.count)
            },
            "requests_hour": {
                "used": hour_state.count,
                "limit": self.config.requests_per_hour,
                "remaining": max(0, self.config.requests_per_hour - hour_state.count)
            },
            "tokens_minute": {
                "used": minute_state.tokens,
                "limit": self.config.tokens_per_minute,
                "remaining": max(0, self.config.tokens_per_minute - minute_state.tokens)
            },
            "concurrent": {
                "used": self._concurrent_requests.get(identifier, 0),
                "limit": self.config.max_concurrent_requests
            }
        }

    def reset(self, user_id: Optional[str] = None) -> None:
        """Reset rate limits for a user (admin function)."""
        if user_id:
            self._user_minute_state.pop(user_id, None)
            self._user_hour_state.pop(user_id, None)
            self._concurrent_requests.pop(user_id, None)
        else:
            self._user_minute_state.clear()
            self._user_hour_state.clear()
            self._concurrent_requests.clear()
            self._global_minute_state = RateLimitState()
            self._global_hour_state = RateLimitState()
            self._global_concurrent = 0

        logger.info("Rate limits reset", user_id=user_id or "all")
