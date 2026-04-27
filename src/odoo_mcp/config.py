"""Runtime settings and credential redaction helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError

from odoo_mcp.exceptions import OdooConfigError
from odoo_mcp.types import JsonValue

REDACTED = "[redacted]"
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
    }
)


class OdooSettings(BaseSettings):
    """Configuration needed to call the Odoo 19 JSON-2 API."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True, enable_decoding=False)

    base_url: str = Field(validation_alias="ODOO_URL")
    api_key: str = Field(validation_alias="ODOO_API_KEY")
    database: str | None = Field(default=None, validation_alias="ODOO_DATABASE")
    timeout_seconds: float = Field(default=30.0, validation_alias="ODOO_TIMEOUT_SECONDS")
    allowed_generic_methods: frozenset[str] = Field(
        default_factory=frozenset,
        validation_alias="ODOO_ALLOWED_GENERIC_METHODS",
    )

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("Odoo URL cannot be empty")
        return normalized

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Odoo API key cannot be empty")
        return value

    @field_validator("database")
    @classmethod
    def normalize_database(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("allowed_generic_methods", mode="before")
    @classmethod
    def parse_allowed_generic_methods(cls, value: object) -> frozenset[str] | object:
        if value is None or isinstance(value, frozenset):
            return value
        if isinstance(value, str):
            return frozenset(item.strip() for item in value.split(",") if item.strip())
        if isinstance(value, Iterable):
            return frozenset(str(item).strip() for item in value if str(item).strip())
        return value


def load_settings() -> OdooSettings:
    """Load settings from the process environment with a safe public error."""

    try:
        return OdooSettings()
    except (SettingsError, ValidationError) as exc:
        raise OdooConfigError(f"Odoo configuration is invalid: {exc}") from exc


def redact_secret(value: str | None) -> str:
    """Return a stable replacement for a secret value."""

    return REDACTED if value else ""


def redact_credentials(value: Any, *, secrets: Iterable[str | None] = ()) -> JsonValue:
    """Recursively redact known credential fields and configured secret values."""

    secret_values = tuple(secret for secret in secrets if secret)
    return _redact_value(value, secret_values=secret_values, sensitive_context=False)


def _redact_value(
    value: Any,
    *,
    secret_values: tuple[str, ...],
    sensitive_context: bool,
) -> JsonValue:
    if sensitive_context:
        return REDACTED
    if isinstance(value, Mapping):
        redacted: dict[str, JsonValue] = {}
        for key, item in value.items():
            key_text = str(key)
            redacted[key_text] = _redact_value(
                item,
                secret_values=secret_values,
                sensitive_context=key_text.lower() in SENSITIVE_KEYS,
            )
        return redacted
    if isinstance(value, list):
        return [
            _redact_value(item, secret_values=secret_values, sensitive_context=False)
            for item in value
        ]
    if isinstance(value, tuple):
        return [
            _redact_value(item, secret_values=secret_values, sensitive_context=False)
            for item in value
        ]
    if isinstance(value, str):
        redacted = value
        for secret in secret_values:
            redacted = redacted.replace(secret, REDACTED)
        return redacted
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
