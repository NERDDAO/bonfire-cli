"""Exception hierarchy for the Bonfires SDK."""

from __future__ import annotations


class BonfiresError(Exception):
    """Base exception for all SDK errors."""


class ConfigError(BonfiresError):
    """Missing or invalid configuration."""


class APIError(BonfiresError):
    """HTTP request failed."""

    def __init__(self, message: str, status_code: int, response_text: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class NotFoundError(BonfiresError):
    """Resource not found — local (kEngram/profile on disk) or remote (404)."""

    def __init__(
        self, message: str, *, status_code: int = 0, response_text: str = ""
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class StorageError(BonfiresError):
    """Local vault/filesystem operation failed."""


class AuthenticationError(APIError):
    """Authentication failed (401/403)."""
