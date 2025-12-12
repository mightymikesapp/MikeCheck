"""Prometheus metrics collection and instrumentation for MikeCheck.

This module provides:
- Counter metrics for request volumes and errors
- Histogram metrics for latency and performance
- Gauge metrics for runtime state
- Middleware for automatic HTTP metrics collection
"""

from typing import Any

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        CollectorRegistry,
        Counter,
        Histogram,
        Gauge,
        generate_latest,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Global registry (use default if available)
registry: CollectorRegistry | None = REGISTRY if PROMETHEUS_AVAILABLE else None

# ============================================================================
# Application Metrics
# ============================================================================

# Tool call metrics
mcp_tool_calls_total: Counter | None = None
mcp_tool_duration_seconds: Histogram | None = None
mcp_tool_errors_total: Counter | None = None

# API request metrics
api_requests_total: Counter | None = None
api_request_duration_seconds: Histogram | None = None
api_request_errors_total: Counter | None = None

# CourtListener API metrics
courtlistener_api_calls_total: Counter | None = None
courtlistener_api_duration_seconds: Histogram | None = None
courtlistener_api_errors_total: Counter | None = None

# Cache metrics
cache_hits_total: Counter | None = None
cache_misses_total: Counter | None = None
cache_size_bytes: Gauge | None = None

# Circuit breaker metrics
circuit_breaker_open_total: Counter | None = None
circuit_breaker_state: Gauge | None = None


def initialize_metrics() -> None:
    """Initialize all Prometheus metrics.

    Should be called once at application startup.
    Safe to call multiple times (idempotent).
    """
    global mcp_tool_calls_total, mcp_tool_duration_seconds, mcp_tool_errors_total
    global api_requests_total, api_request_duration_seconds, api_request_errors_total
    global courtlistener_api_calls_total, courtlistener_api_duration_seconds
    global courtlistener_api_errors_total
    global cache_hits_total, cache_misses_total, cache_size_bytes
    global circuit_breaker_open_total, circuit_breaker_state

    if not PROMETHEUS_AVAILABLE:
        return

    # Tool metrics
    mcp_tool_calls_total = Counter(
        "mcp_tool_calls_total",
        "Total MCP tool invocations",
        ["tool_name", "status"],
        registry=registry,
    )
    mcp_tool_duration_seconds = Histogram(
        "mcp_tool_duration_seconds",
        "MCP tool execution duration",
        ["tool_name"],
        buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
        registry=registry,
    )
    mcp_tool_errors_total = Counter(
        "mcp_tool_errors_total",
        "Total MCP tool errors",
        ["tool_name", "error_type"],
        registry=registry,
    )

    # API metrics
    api_requests_total = Counter(
        "api_requests_total",
        "Total API requests",
        ["method", "endpoint", "status_code"],
        registry=registry,
    )
    api_request_duration_seconds = Histogram(
        "api_request_duration_seconds",
        "API request duration",
        ["method", "endpoint"],
        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        registry=registry,
    )
    api_request_errors_total = Counter(
        "api_request_errors_total",
        "Total API request errors",
        ["method", "endpoint", "error_type"],
        registry=registry,
    )

    # CourtListener API metrics
    courtlistener_api_calls_total = Counter(
        "courtlistener_api_calls_total",
        "Total CourtListener API calls",
        ["endpoint", "status_code"],
        registry=registry,
    )
    courtlistener_api_duration_seconds = Histogram(
        "courtlistener_api_duration_seconds",
        "CourtListener API call duration",
        ["endpoint"],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
        registry=registry,
    )
    courtlistener_api_errors_total = Counter(
        "courtlistener_api_errors_total",
        "Total CourtListener API errors",
        ["endpoint", "error_code"],
        registry=registry,
    )

    # Cache metrics
    cache_hits_total = Counter(
        "cache_hits_total",
        "Total cache hits",
        ["cache_type"],
        registry=registry,
    )
    cache_misses_total = Counter(
        "cache_misses_total",
        "Total cache misses",
        ["cache_type"],
        registry=registry,
    )
    cache_size_bytes = Gauge(
        "cache_size_bytes",
        "Cache size in bytes",
        ["cache_type"],
        registry=registry,
    )

    # Circuit breaker metrics
    circuit_breaker_open_total = Counter(
        "circuit_breaker_open_total",
        "Total circuit breaker open events",
        ["service"],
        registry=registry,
    )
    circuit_breaker_state = Gauge(
        "circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=open)",
        ["service"],
        registry=registry,
    )


def metrics_available() -> bool:
    """Check if Prometheus metrics are available.

    Returns:
        True if prometheus_client is installed, False otherwise.
    """
    return PROMETHEUS_AVAILABLE


def get_metrics_response() -> tuple[bytes, str]:
    """Get Prometheus metrics in text format.

    Returns:
        Tuple of (metrics_bytes, content_type)
        Returns empty metrics if prometheus_client not installed.
    """
    if not PROMETHEUS_AVAILABLE or registry is None:
        return b"", "text/plain; version=0.0.4"

    return generate_latest(registry), CONTENT_TYPE_LATEST


def record_tool_call(tool_name: str, duration_seconds: float, error: bool = False) -> None:
    """Record a tool call metric.

    Args:
        tool_name: Name of the tool
        duration_seconds: Execution duration
        error: Whether the call resulted in an error
    """
    if not PROMETHEUS_AVAILABLE or mcp_tool_calls_total is None:
        return

    status = "error" if error else "success"
    mcp_tool_calls_total.labels(tool_name=tool_name, status=status).inc()
    mcp_tool_duration_seconds.labels(tool_name=tool_name).observe(duration_seconds)


def record_tool_error(tool_name: str, error_type: str) -> None:
    """Record a tool error metric.

    Args:
        tool_name: Name of the tool
        error_type: Type of error (e.g., "timeout", "api_error")
    """
    if not PROMETHEUS_AVAILABLE or mcp_tool_errors_total is None:
        return

    mcp_tool_errors_total.labels(tool_name=tool_name, error_type=error_type).inc()


def record_api_request(
    method: str, endpoint: str, status_code: int, duration_seconds: float
) -> None:
    """Record an API request metric.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
        status_code: HTTP status code
        duration_seconds: Request duration
    """
    if not PROMETHEUS_AVAILABLE or api_requests_total is None or api_request_duration_seconds is None:
        return

    api_requests_total.labels(
        method=method, endpoint=endpoint, status_code=status_code
    ).inc()
    api_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
        duration_seconds
    )


def record_api_error(method: str, endpoint: str, error_type: str) -> None:
    """Record an API error metric.

    Args:
        method: HTTP method
        endpoint: API endpoint path
        error_type: Type of error
    """
    if not PROMETHEUS_AVAILABLE or api_request_errors_total is None:
        return

    api_request_errors_total.labels(
        method=method, endpoint=endpoint, error_type=error_type
    ).inc()


def record_courtlistener_call(
    endpoint: str, status_code: int, duration_seconds: float
) -> None:
    """Record a CourtListener API call.

    Args:
        endpoint: API endpoint
        status_code: HTTP status code
        duration_seconds: Request duration
    """
    if not PROMETHEUS_AVAILABLE or courtlistener_api_calls_total is None:
        return

    courtlistener_api_calls_total.labels(endpoint=endpoint, status_code=status_code).inc()
    courtlistener_api_duration_seconds.labels(endpoint=endpoint).observe(duration_seconds)


def record_courtlistener_error(endpoint: str, error_code: int | str) -> None:
    """Record a CourtListener API error.

    Args:
        endpoint: API endpoint
        error_code: Error code or type
    """
    if not PROMETHEUS_AVAILABLE or courtlistener_api_errors_total is None:
        return

    courtlistener_api_errors_total.labels(endpoint=endpoint, error_code=str(error_code)).inc()


def record_cache_hit(cache_type: str) -> None:
    """Record a cache hit.

    Args:
        cache_type: Type of cache (e.g., "metadata", "text")
    """
    if not PROMETHEUS_AVAILABLE or cache_hits_total is None:
        return

    cache_hits_total.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str) -> None:
    """Record a cache miss.

    Args:
        cache_type: Type of cache
    """
    if not PROMETHEUS_AVAILABLE or cache_misses_total is None:
        return

    cache_misses_total.labels(cache_type=cache_type).inc()


def set_cache_size(cache_type: str, size_bytes: int) -> None:
    """Set cache size gauge.

    Args:
        cache_type: Type of cache
        size_bytes: Size in bytes
    """
    if not PROMETHEUS_AVAILABLE or cache_size_bytes is None:
        return

    cache_size_bytes.labels(cache_type=cache_type).set(size_bytes)


def record_circuit_breaker_open(service: str) -> None:
    """Record circuit breaker opening.

    Args:
        service: Name of service (e.g., "courtlistener")
    """
    if not PROMETHEUS_AVAILABLE or circuit_breaker_open_total is None:
        return

    circuit_breaker_open_total.labels(service=service).inc()
    circuit_breaker_state.labels(service=service).set(1)  # 1 = open


def set_circuit_breaker_state(service: str, is_open: bool) -> None:
    """Set circuit breaker state.

    Args:
        service: Name of service
        is_open: Whether circuit breaker is open
    """
    if not PROMETHEUS_AVAILABLE or circuit_breaker_state is None:
        return

    state_value = 1 if is_open else 0
    circuit_breaker_state.labels(service=service).set(state_value)
