"""Authentication and authorization for MikeCheck API.

This module provides:
- API key validation and verification
- Request authentication middleware
- Token generation and management
- Role-based access control
"""

import hashlib
import logging
from typing import Optional

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


class APIKeyManager:
    """Manage and validate API keys."""

    def __init__(self) -> None:
        """Initialize API key manager with valid keys from environment."""
        # In production, these would be loaded from a secure vault
        # For now, we validate against configured keys
        self.valid_keys: set[str] = set()
        self._load_keys()

    def _load_keys(self) -> None:
        """Load valid API keys from environment or database."""
        from app.config import settings

        # Load from settings (comma-separated list)
        if settings.api_keys:
            keys = [k.strip() for k in settings.api_keys.split(",") if k.strip()]
            self.valid_keys = set(keys)
            logger.info(f"Loaded {len(self.valid_keys)} API keys")

    def validate_key(self, api_key: str) -> bool:
        """Validate an API key.

        Args:
            api_key: The API key to validate

        Returns:
            True if valid, False otherwise
        """
        if not api_key:
            return False

        # Simple validation for now - just check if key is in valid set
        # In production, could implement key rotation, expiration, etc.
        is_valid = api_key in self.valid_keys
        if not is_valid:
            logger.warning(f"Invalid API key attempt: {self._hash_key(api_key)}")
        return is_valid

    @staticmethod
    def _hash_key(api_key: str) -> str:
        """Hash a key for logging (never log raw keys)."""
        return hashlib.sha256(api_key.encode()).hexdigest()[:12]

    def get_key_info(self, api_key: str) -> dict[str, str | None]:
        """Get metadata about a key (for future use).

        Args:
            api_key: The API key

        Returns:
            Dictionary with key metadata
        """
        if not self.validate_key(api_key):
            return {"valid": False, "key_hash": self._hash_key(api_key)}

        return {
            "valid": True,
            "key_hash": self._hash_key(api_key),
            "rate_limit": "standard",  # Could be dynamic in future
        }


# Global API key manager
_api_key_manager: Optional[APIKeyManager] = None


def get_api_key_manager() -> APIKeyManager:
    """Get or create the global API key manager."""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager


async def verify_api_key(request: Request) -> Optional[str]:
    """Verify API key from request headers or query params.

    Args:
        request: FastAPI request object

    Returns:
        The validated API key or None when authentication is disabled

    Raises:
        HTTPException: If key is invalid or missing
    """
    from app.config import settings

    # Skip authentication if disabled
    if not settings.enable_api_key_auth:
        return None

    # Try to get API key from multiple sources
    api_key = None

    # 1. Check Authorization header (Bearer token)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]  # Remove "Bearer " prefix

    # 2. Check X-API-Key header
    if not api_key:
        api_key = request.headers.get("X-API-Key", "")

    # 3. Check query parameter (less secure, but useful for development)
    if not api_key and "api_key" in request.query_params:
        api_key = request.query_params.get("api_key", "")
        logger.warning(
            "API key provided via query parameter (less secure than headers)",
            extra={"event": "api_key_query_param"},
        )

    # Validate key
    if not api_key:
        logger.warning(
            "Missing API key",
            extra={
                "event": "missing_api_key",
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Use header: Authorization: Bearer YOUR_KEY or X-API-Key: YOUR_KEY",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify key
    manager = get_api_key_manager()
    if not manager.validate_key(api_key):
        logger.warning(
            "Invalid API key",
            extra={
                "event": "invalid_api_key",
                "method": request.method,
                "path": request.url.path,
                "key_hash": APIKeyManager._hash_key(api_key),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return api_key


def get_public_endpoints() -> list[str]:
    """Get list of endpoints that don't require authentication.

    Returns:
        List of public endpoint paths
    """
    return [
        "/health",
        "/metrics",
        "/",
        "/docs",
        "/openapi.json",
        "/redoc",
    ]


def is_public_endpoint(path: str) -> bool:
    """Check if an endpoint is public (doesn't require auth).

    Args:
        path: The request path

    Returns:
        True if endpoint is public, False otherwise
    """
    public = get_public_endpoints()
    return any(path == p or path.startswith(p + "/") for p in public)


__all__ = [
    "APIKeyManager",
    "get_api_key_manager",
    "verify_api_key",
    "get_public_endpoints",
    "is_public_endpoint",
]
