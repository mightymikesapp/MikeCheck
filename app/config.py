"""Configuration management for Legal Research Assistant MCP."""

from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field

from app.logging_config import configure_logging
from app.settings_base import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    mode: Literal["light", "standard", "heavy"] = Field(
        default="standard",
        description=(
            "Preset configuration profile. "
            "Use 'light' for quick checks, 'standard' for balanced runs, and 'heavy' for deep dives."
        ),
    )

    # CourtListener MCP connection
    courtlistener_mcp_url: str = Field(
        default="http://localhost:8000/mcp/",
        description="URL for CourtListener MCP server",
    )

    # CourtListener API configuration
    courtlistener_api_key: str | None = Field(
        default=None,
        description="API key for CourtListener requests",
        validation_alias=AliasChoices("COURT_LISTENER_API_KEY", "COURTLISTENER_API_KEY"),
    )
    courtlistener_base_url: str = Field(
        default="https://www.courtlistener.com/api/rest/v4/",
        description="Base URL for CourtListener API requests",
    )
    courtlistener_timeout: float = Field(
        default=30.0,
        description="Request timeout (seconds) for CourtListener API calls",
    )
    courtlistener_connect_timeout: float = Field(
        default=10.0,
        description="Connect timeout (seconds) for CourtListener API calls",
    )
    courtlistener_read_timeout: float = Field(
        default=60.0,
        description="Read timeout (seconds) for CourtListener API calls",
    )
    courtlistener_retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for CourtListener API requests",
    )
    courtlistener_retry_backoff: float = Field(
        default=1.0,
        description="Initial backoff (seconds) for retrying CourtListener API requests",
    )
    # Cache configuration
    cache_enabled: bool = Field(
        default=True,
        description="Global master switch for caching",
    )
    cache_dir: Path = Field(
        default=Path(".cache"),
        description="Base directory for all cache data",
    )
    courtlistener_cache_dir: Path = Field(
        default=Path(".cache/courtlistener"),
        description="Directory for caching CourtListener API responses",
    )

    # Granular TTLs
    courtlistener_ttl_metadata: int = Field(
        default=86400,  # 24 hours
        description="TTL (seconds) for case metadata",
    )
    courtlistener_ttl_text: int = Field(
        default=604800,  # 7 days
        description="TTL (seconds) for opinion text",
    )
    courtlistener_ttl_search: int = Field(
        default=3600,  # 1 hour
        description="TTL (seconds) for search results",
    )
    courtlistener_search_cache_enabled: bool = Field(
        default=True,
        description="Enable or disable caching for search endpoints",
    )

    # Server configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(
        default="json",
        description="Logging format string or 'json' for structured logging",
    )
    log_date_format: str = Field(
        default="%Y-%m-%d %H:%M:%S",
        description="Date format for log messages",
    )
    debug: bool = Field(default=False, description="Debug mode")
    mcp_port: int = Field(default=8001, description="MCP server port")

    # Treatment analysis settings
    treatment_confidence_threshold: float = Field(
        default=0.7,
        description="Minimum confidence threshold for validity assessments",
    )
    max_citing_cases: int = Field(
        default=100,
        description="Maximum number of citing cases to analyze",
    )
    fetch_full_text_strategy: str = Field(
        default="smart",
        description="When to fetch full opinion text: 'always', 'smart', 'negative_only', 'never'",
    )
    max_full_text_fetches: int = Field(
        default=10,
        description="Maximum number of full opinion texts to fetch per analysis",
    )

    # Citation network settings
    network_max_depth: int = Field(
        default=3,
        description="Maximum depth for citation network traversal",
    )
    max_total_network_nodes: int = Field(
        default=300,
        description="Maximum total nodes allowed in a citation network request",
        validation_alias=AliasChoices("MAX_TOTAL_NETWORK_NODES"),
    )
    max_quotes_per_batch: int = Field(
        default=50,
        description="Maximum quotes that can be verified in a single batch",
        validation_alias=AliasChoices("MAX_QUOTES_PER_BATCH"),
    )
    network_cache_dir: Path = Field(
        default=Path("./citation_networks"),
        description="Directory for caching citation network data",
    )

    # CORS configuration
    cors_origins: str = Field(
        default="http://localhost:8000,http://127.0.0.1:8000",
        description="Comma-separated list of allowed CORS origins",
    )
    cors_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests",
    )
    cors_methods: str = Field(
        default="GET,POST,PUT,DELETE,OPTIONS",
        description="Comma-separated list of allowed CORS methods",
    )
    cors_headers: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS headers",
    )

    # Security headers
    enable_hsts: bool = Field(
        default=False,  # Set to True in production
        description="Enable HSTS (HTTP Strict Transport Security) header",
    )
    hsts_max_age: int = Field(
        default=31536000,  # 1 year
        description="HSTS max-age in seconds",
    )
    enable_csp: bool = Field(
        default=True,
        description="Enable Content Security Policy (CSP) header",
    )
    csp_policy: str = Field(
        default="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
        description="Content Security Policy directive",
    )

    # Authentication configuration
    enable_api_key_auth: bool = Field(
        default=False,
        description="Enable API key authentication for all protected endpoints",
    )
    api_keys: str = Field(
        default="",
        description="Comma-separated list of valid API keys (empty = disabled)",
    )

    # Rate limiting configuration
    enable_rate_limiting: bool = Field(
        default=True,
        description="Enable rate limiting for API endpoints",
    )
    rate_limit_default: str = Field(
        default="100/minute",
        description="Default rate limit for all endpoints (e.g., '100/minute', '10/hour')",
    )
    rate_limit_treatment_analysis: str = Field(
        default="5/minute",
        description="Rate limit for treatment analysis endpoints",
    )
    rate_limit_bulk_operations: str = Field(
        default="2/minute",
        description="Rate limit for bulk operation endpoints",
    )
    rate_limit_semantic_search: str = Field(
        default="20/minute",
        description="Rate limit for semantic search endpoints",
    )

    def model_post_init(self, __context: Any) -> None:
        """Apply mode-specific defaults while preserving explicit overrides."""
        super().model_post_init(__context)
        self._apply_mode_defaults()

    def _apply_mode_defaults(self) -> None:
        """Apply preset values for the selected mode unless explicitly overridden."""

        profiles: dict[str, dict[str, Any]] = {
            "light": {
                "max_citing_cases": 25,
                "max_full_text_fetches": 3,
                "courtlistener_timeout": 15.0,
                "courtlistener_connect_timeout": 5.0,
                "courtlistener_read_timeout": 30.0,
                "courtlistener_retry_attempts": 2,
                "courtlistener_retry_backoff": 0.5,
                "courtlistener_ttl_metadata": 3600,
                "courtlistener_ttl_text": 86400,
                "courtlistener_ttl_search": 1800,
            },
            "standard": {
                "max_citing_cases": 100,
                "max_full_text_fetches": 10,
                "courtlistener_timeout": 30.0,
                "courtlistener_connect_timeout": 10.0,
                "courtlistener_read_timeout": 60.0,
                "courtlistener_retry_attempts": 3,
                "courtlistener_retry_backoff": 1.0,
                "courtlistener_ttl_metadata": 86400,
                "courtlistener_ttl_text": 604800,
                "courtlistener_ttl_search": 3600,
            },
            "heavy": {
                "max_citing_cases": 200,
                "max_full_text_fetches": 25,
                "fetch_full_text_strategy": "always",
                "courtlistener_timeout": 45.0,
                "courtlistener_connect_timeout": 15.0,
                "courtlistener_read_timeout": 120.0,
                "courtlistener_retry_attempts": 5,
                "courtlistener_retry_backoff": 2.0,
                "courtlistener_ttl_metadata": 172800,
                "courtlistener_ttl_text": 1209600,
                "courtlistener_ttl_search": 14400,
                "network_max_depth": 4,
            },
        }

        profile_overrides = profiles.get(self.mode, {})
        for field_name, value in profile_overrides.items():
            if field_name in self.model_fields_set:
                continue
            setattr(self, field_name, value)

    def configure_logging(self) -> None:
        """Configure application logging."""
        configure_logging(self.log_level, self.log_format, self.log_date_format)


# Global settings instance
settings = Settings()
settings.configure_logging()

# Create cache directory if it doesn't exist
settings.network_cache_dir.mkdir(parents=True, exist_ok=True)
settings.courtlistener_cache_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings
