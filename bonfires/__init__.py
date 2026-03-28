"""Bonfires — SDK and CLI for the Bonfires AI API."""

__version__ = "0.4.0"

from bonfires.sdk import BonfiresClient, BonfiresConfig
from bonfires.sdk.exceptions import (
    APIError,
    AuthenticationError,
    BonfiresError,
    ConfigError,
    NotFoundError,
    StorageError,
)

__all__ = [
    "__version__",
    "BonfiresClient",
    "BonfiresConfig",
    "BonfiresError",
    "ConfigError",
    "APIError",
    "NotFoundError",
    "StorageError",
    "AuthenticationError",
]
