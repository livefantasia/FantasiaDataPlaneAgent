"""DataPlane Agent package.

A lightweight bridge between AudioAPIServer instances and the centralized ControlPlane,
focusing on usage tracking, session management, and basic server administration.
"""

__version__ = "1.0.0"
__author__ = "SpeechEngine Team"
__description__ = "DataPlane Agent for SpeechEngine platform"

from main import app, create_app

__all__ = ["app", "create_app"]
