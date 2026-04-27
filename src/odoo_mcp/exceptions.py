"""Project exceptions and safe error helpers."""

from __future__ import annotations


class OdooMCPError(RuntimeError):
    """Base class for server errors that are safe to expose to MCP callers."""


class OdooConfigError(OdooMCPError):
    """Configuration is missing or invalid."""


class OdooAPIError(OdooMCPError):
    """Odoo returned an error response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OdooSafetyError(OdooMCPError):
    """A requested operation failed local MCP safety policy."""
