"""Configuration classes for DataPlane Agent.

This module contains all configuration classes organized by domain.
Configuration is loaded from environment variables and .env files.
"""

from typing import Any, List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def str_to_bool(value: Any) -> bool:
    """Convert various string representations to boolean values.
    
    This function provides consistent boolean conversion from environment variables
    and other string sources. It can be used as a field validator for Pydantic models.
    
    Args:
        value: The value to convert. Can be bool, str, int, or any other type.
        
    Returns:
        bool: The converted boolean value.
        
    Examples:
        >>> str_to_bool("true")
        True
        >>> str_to_bool("false")
        False
        >>> str_to_bool("1")
        True
        >>> str_to_bool("0")
        False
        >>> str_to_bool("yes")
        True
        >>> str_to_bool("no")
        False
        
        # Usage in Pydantic field validators:
        @field_validator("my_bool_field", mode="before")
        @classmethod
        def validate_my_bool_field(cls, v) -> bool:
            return str_to_bool(v)
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on", "enabled")
    if isinstance(value, int):
        return bool(value)
    return bool(value)


class ServerConfig(BaseSettings):
    """Server configuration settings."""

    # Application metadata
    app_name: str = "DataPlane Agent"
    app_version: str = "1.0.0"
    debug: bool = False

    # Server configuration
    server_id: str = Field(default="", alias="SERVER_ID")
    server_region: str = Field(default="", alias="SERVER_REGION")
    server_port: int = Field(default=8081, alias="SERVER_PORT")
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_ip: str = Field(default="0.0.0.0", alias="SERVER_IP")


class RedisConfig(BaseSettings):
    """Redis configuration settings."""

    # Redis configuration
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")
    redis_db: int = Field(default=0, alias="REDIS_DB")
    redis_socket_timeout: int = 30
    redis_retry_on_timeout: bool = True
    redis_max_connections: int = 10

    # Queue names
    usage_records_queue: str = "queue:usage_records"
    session_lifecycle_queue: str = "queue:session_lifecycle"
    quota_refresh_queue: str = "queue:quota_refresh"
    quota_response_queue: str = "queue:quota_response"
    dead_letter_queue: str = "queue:dead_letter"


class ControlPlaneConfig(BaseSettings):
    """ControlPlane configuration settings."""

    # ControlPlane configuration
    control_plane_url: str = Field(default="", alias="CONTROL_PLANE_URL")
    control_plane_api_key: str = Field(default="", alias="CONTROL_PLANE_API_KEY")
    control_plane_health_check_enabled: bool = Field(
        default=True, alias="CONTROL_PLANE_HEALTH_CHECK_ENABLED"
    )
    control_plane_timeout: int = 30
    control_plane_retry_attempts: int = 3
    control_plane_retry_backoff_factor: float = 2.0
    jwt_public_keys_cache_ttl: int = 3600

    @field_validator("control_plane_health_check_enabled", mode="before")
    @classmethod
    def validate_control_plane_health_check_enabled(cls, v) -> bool:
        """Convert string boolean values to actual boolean."""
        return str_to_bool(v)

    @field_validator("control_plane_url")
    @classmethod
    def validate_control_plane_url(cls, v: str) -> str:
        """Ensure ControlPlane URL is properly formatted."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("control_plane_url must start with http:// or https://")
        return v.rstrip("/")


class MonitoringConfig(BaseSettings):
    """Monitoring configuration settings."""

    # Monitoring configuration
    heartbeat_interval: int = 60
    metrics_port: int = 9090
    health_check_port: int = 8081
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_retention_days: int = 7
    command_poll_interval: int = 60
    command_cache_ttl: int = 86400

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of: {valid_levels}")
        return v.upper()


class SecurityConfig(BaseSettings):
    """Security configuration settings."""

    # Security configuration
    enable_tls: bool = True
    jwt_algorithm: str = "RS256"
    api_key_header: str = "X-API-Key"
    trusted_ips: List[str] = Field(default_factory=list)


class ApplicationConfig(
    ServerConfig,
    RedisConfig,
    ControlPlaneConfig,
    MonitoringConfig,
    SecurityConfig,
    BaseSettings
):
    """Main application configuration that combines all configuration domains."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )