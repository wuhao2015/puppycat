from __future__ import annotations


class PuppycatError(Exception):
    """Base class for application errors that map to clean HTTP responses."""

    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BudgetExceededError(PuppycatError):
    status_code = 429


class UpstreamUnavailableError(PuppycatError):
    status_code = 502


class ConfigurationError(PuppycatError):
    status_code = 500
