"""Domain errors shared by HTTP and provider layers."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: int, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def bad_request(message: str, code: int = 40001, field: str | None = None) -> ApiError:
    details = {"field": field} if field else None
    return ApiError(400, code, message, details)


class ProviderError(Exception):
    code = "provider_error"


class ProviderAuthError(ProviderError):
    code = "provider_auth_failed"


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limited"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"
