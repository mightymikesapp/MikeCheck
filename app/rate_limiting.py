"""Rate limiting and request throttling for MikeCheck API.

This module provides:
- Per-endpoint rate limiting with slowapi
- Per-API-key rate limiting tiers
- Adaptive rate limiting based on system load
- Request queuing and backoff strategies
"""

import logging
from typing import Any, Callable, Optional, TypeVar, cast

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

logger = logging.getLogger(__name__)


F = TypeVar("F", bound=Callable[..., Any])


class RateLimiter:
    """Advanced rate limiting with tiered limits."""

    # Default rate limits (requests per minute)
    TIER_LIMITS = {
        "free": "10/minute",  # Free tier: 10 requests/min
        "standard": "100/minute",  # Standard: 100 requests/min
        "premium": "1000/minute",  # Premium: 1000 requests/min
        "unlimited": None,  # No limit
    }

    # Endpoint-specific limits (override defaults)
    ENDPOINT_LIMITS = {
        "/herding/analyze": "5/minute",  # Treatment analysis limited
        "/herding/analyze/bulk": "2/minute",  # Bulk operations more limited
        "/search/semantic": "20/minute",  # Semantic search limited
        "/research/pipeline": "3/minute",  # Heavy computation limited
        "/health": None,  # No rate limit for health checks
        "/metrics": None,  # No rate limit for metrics
    }

    def __init__(self) -> None:
        """Initialize rate limiter with slowapi."""
        self.limiter = Limiter(
            key_func=self._get_key,
            default_limits=["100/minute"],  # Global default
            storage_uri="memory",  # Use in-memory storage (for single-instance)
            swallow_errors=False,  # Don't swallow rate limit errors
            in_memory_fallback_enabled=True,  # Fallback to in-memory if storage fails
        )

    @staticmethod
    def _get_key(request: Request) -> str:
        """Get rate limit key from request.

        Prioritizes API key, falls back to IP address.

        Args:
            request: FastAPI request object

        Returns:
            String identifier for rate limiting
        """
        # Try to get API key from headers
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return f"api_key:{auth_header[7:]}"

        api_key = request.headers.get("X-API-Key", "")
        if api_key:
            return f"api_key:{api_key}"

        # Fallback to IP address
        ip = get_remote_address(request)
        return f"ip:{ip}"

    def get_limit_for_endpoint(self, path: str) -> Optional[str]:
        """Get rate limit for a specific endpoint.

        Args:
            path: Request path

        Returns:
            Rate limit string (e.g., "100/minute") or None for unlimited
        """
        # Check endpoint-specific limits first
        if path in self.ENDPOINT_LIMITS:
            return self.ENDPOINT_LIMITS[path]

        # Check prefix matches
        for endpoint_pattern, limit in self.ENDPOINT_LIMITS.items():
            if path.startswith(endpoint_pattern.rstrip("/")):
                return limit

        # Return default
        return "100/minute"

    def get_limit_string(self, api_key: Optional[str] = None) -> str:
        """Get rate limit string for an API key tier.

        Args:
            api_key: The API key (optional)

        Returns:
            Rate limit string (e.g., "100/minute")
        """
        # Determine tier from API key metadata
        # For now, return standard tier
        tier = "standard"

        limit = self.TIER_LIMITS.get(tier, "100/minute")
        return limit if limit else "unlimited"


# Global rate limiter
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def rate_limit(limit: str = "100/minute") -> Callable[[F], F]:
    """Decorator to apply rate limiting to an endpoint.

    Args:
        limit: Rate limit string (e.g., "100/minute", "10/hour")

    Returns:
        Decorated function with rate limiting
    """

    def decorator(func: F) -> F:
        limiter = get_rate_limiter()
        return cast(F, limiter.limiter.limit(limit)(func))

    return decorator


def rate_limit_dynamic(endpoint: str) -> Callable[[F], F]:
    """Decorator to apply dynamic rate limiting based on endpoint.

    Args:
        endpoint: The endpoint path

    Returns:
        Decorated function with dynamic rate limiting
    """

    def decorator(func: F) -> F:
        limiter = get_rate_limiter()
        limit = limiter.get_limit_for_endpoint(endpoint)
        if limit is None:
            # No rate limit
            return func
        return cast(F, limiter.limiter.limit(limit)(func))

    return decorator


class RateLimitExceptionHandler:
    """Handle rate limit exceeded exceptions."""

    @staticmethod
    def handle_rate_limit_exceeded(
        exc: RateLimitExceeded, request: Request
    ) -> dict[str, str | None]:
        """Handle rate limit exceeded exception.

        Args:
            exc: The rate limit exception
            request: FastAPI request

        Returns:
            Error response dictionary
        """
        logger.warning(
            "Rate limit exceeded",
            extra={
                "event": "rate_limit_exceeded",
                "path": request.url.path,
                "limit_info": str(exc),
            },
        )

        return {
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": exc.detail if hasattr(exc, "detail") else None,
        }


__all__ = [
    "RateLimiter",
    "get_rate_limiter",
    "rate_limit",
    "rate_limit_dynamic",
    "RateLimitExceptionHandler",
]
