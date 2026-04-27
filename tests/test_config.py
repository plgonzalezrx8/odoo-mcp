from __future__ import annotations

import pytest

from odoo_mcp.config import OdooSettings, load_settings, redact_credentials, redact_secret
from odoo_mcp.exceptions import OdooConfigError


def test_load_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ODOO_URL", "https://example.odoo.com/")
    monkeypatch.setenv("ODOO_API_KEY", "super-secret-token")
    monkeypatch.setenv("ODOO_DATABASE", "prod")
    monkeypatch.setenv("ODOO_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("ODOO_ALLOWED_GENERIC_METHODS", "call_kw,execute_kw")

    settings = load_settings()

    assert settings.base_url == "https://example.odoo.com"
    assert settings.api_key == "super-secret-token"
    assert settings.database == "prod"
    assert settings.timeout_seconds == 12
    assert settings.allowed_generic_methods == frozenset({"call_kw", "execute_kw"})


def test_load_settings_maps_validation_errors() -> None:
    with pytest.raises(OdooConfigError) as exc_info:
        load_settings()

    assert "Odoo configuration is invalid" in str(exc_info.value)


def test_settings_normalize_base_url() -> None:
    settings = OdooSettings(base_url="https://example.odoo.com//", api_key="secret")

    assert settings.base_url == "https://example.odoo.com"


def test_redact_secret_never_exposes_value() -> None:
    redacted = redact_secret("super-secret-token")

    assert redacted == "[redacted]"
    assert "super-secret-token" not in redacted


def test_redact_credentials_handles_nested_headers() -> None:
    payload = {
        "headers": {"Authorization": "Bearer super-secret-token"},
        "body": {"api_key": "super-secret-token", "safe": "value"},
        "items": [{"password": "super-secret-token"}],
    }

    redacted = redact_credentials(payload, secrets=("super-secret-token",))

    assert redacted == {
        "headers": {"Authorization": "[redacted]"},
        "body": {"api_key": "[redacted]", "safe": "value"},
        "items": [{"password": "[redacted]"}],
    }
