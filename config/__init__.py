"""Configuration management for DataPlane Agent.

This module handles all configuration loading and validation using Pydantic BaseSettings.
Configuration is loaded from environment variables and .env files.
"""

from .config import (
    ApplicationConfig,
    ServerConfig,
    RedisConfig,
    ControlPlaneConfig,
    MonitoringConfig,
    SecurityConfig,
    str_to_bool,
)


def load_config() -> ApplicationConfig:
    """Load and validate application configuration."""
    return ApplicationConfig()


__all__ = [
    "ApplicationConfig",
    "ServerConfig",
    "RedisConfig",
    "ControlPlaneConfig",
    "MonitoringConfig",
    "SecurityConfig",
    "load_config",
    "str_to_bool",
]
