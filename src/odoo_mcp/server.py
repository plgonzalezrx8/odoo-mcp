"""Shared FastMCP server factory and runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP

from odoo_mcp import __version__
from odoo_mcp.exceptions import OdooConfigError
from odoo_mcp.odoo_client import LazyOdooClient
from odoo_mcp.prompts import register_prompts
from odoo_mcp.resources import register_resources
from odoo_mcp.tools.crm import register_crm_tools
from odoo_mcp.tools.generic import register_generic_tools
from odoo_mcp.types import JsonObject, JsonValue

SERVER_NAME = "odoo-mcp"
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8000
DEFAULT_HTTP_PATH = "/mcp"
DEFAULT_LOG_LEVEL = "info"

_REDACTED = "***"
_SENSITIVE_KEYS = {"odoo_api_key", "mcp_static_token", "jwt_public_key"}


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Runtime settings consumed by the server factory and CLI."""

    odoo_url: str | None = None
    odoo_database: str | None = None
    odoo_api_key: str | None = None
    allowed_generic_methods: str | None = None
    crm_optional_features: tuple[str, ...] = ()
    mcp_auth_mode: str = "none"
    mcp_static_token: str | None = None
    jwt_jwks_uri: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_public_key: str | None = None
    jwt_required_scopes: tuple[str, ...] = ()
    http_host: str = DEFAULT_HTTP_HOST
    http_port: int = DEFAULT_HTTP_PORT
    http_path: str = DEFAULT_HTTP_PATH
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> RuntimeConfig:
        env = os.environ if environ is None else environ
        return cls(
            odoo_url=_empty_to_none(env.get("ODOO_URL")),
            odoo_database=_empty_to_none(env.get("ODOO_DATABASE")),
            odoo_api_key=_empty_to_none(env.get("ODOO_API_KEY")),
            allowed_generic_methods=_empty_to_none(env.get("ODOO_ALLOWED_GENERIC_METHODS")),
            crm_optional_features=_csv_tuple(env.get("ODOO_CRM_OPTIONAL_FEATURES")),
            mcp_auth_mode=env.get("MCP_AUTH_MODE", "none").strip().lower() or "none",
            mcp_static_token=_empty_to_none(env.get("MCP_STATIC_TOKEN")),
            jwt_jwks_uri=_empty_to_none(env.get("JWT_JWKS_URI")),
            jwt_issuer=_empty_to_none(env.get("JWT_ISSUER")),
            jwt_audience=_empty_to_none(env.get("JWT_AUDIENCE")),
            jwt_public_key=_empty_to_none(env.get("JWT_PUBLIC_KEY")),
            jwt_required_scopes=_csv_tuple(env.get("JWT_REQUIRED_SCOPES")),
            http_host=env.get("MCP_HTTP_HOST", DEFAULT_HTTP_HOST),
            http_port=_parse_port(env.get("MCP_HTTP_PORT", str(DEFAULT_HTTP_PORT))),
            http_path=_normalize_path(env.get("MCP_HTTP_PATH", DEFAULT_HTTP_PATH)),
            log_level=env.get("MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL),
        )

    @property
    def odoo_configured(self) -> bool:
        return bool(self.odoo_url and self.odoo_api_key)

    def public_dict(self) -> JsonObject:
        payload: JsonObject = {}
        for key, value in _config_items(self).items():
            if value is None:
                continue
            if key in _SENSITIVE_KEYS:
                payload[key] = _REDACTED
            else:
                payload[key] = value
        payload["odoo_configured"] = self.odoo_configured
        return payload


def build_server(config: RuntimeConfig | None = None) -> FastMCP:
    """Build the shared FastMCP server used by HTTP, stdio, and tests."""

    runtime_config = RuntimeConfig.from_env() if config is None else config
    server = FastMCP(
        name=SERVER_NAME,
        version=__version__,
        instructions=(
            "FastMCP bridge for Odoo JSON-2. Use healthcheck to verify that "
            "the server process is ready before calling Odoo tools."
        ),
        auth=_build_auth(runtime_config),
        mask_error_details=True,
        strict_input_validation=True,
        list_page_size=100,
    )

    @server.tool(name="healthcheck", description="Return local server readiness metadata.")
    def healthcheck_tool() -> dict[str, Any]:
        return healthcheck_payload(runtime_config)

    _register_odoo_components(server, runtime_config)
    return server


def create_mcp(config: RuntimeConfig | None = None) -> FastMCP:
    """Compatibility alias for users expecting a create_mcp factory."""

    return build_server(config)


def inspect_config(config: RuntimeConfig | None = None) -> JsonObject:
    runtime_config = RuntimeConfig.from_env() if config is None else config
    return runtime_config.public_dict()


def healthcheck_payload(config: RuntimeConfig | None = None) -> JsonObject:
    runtime_config = RuntimeConfig.from_env() if config is None else config
    return {
        "status": "ok",
        "server": SERVER_NAME,
        "version": __version__,
        "odoo_configured": runtime_config.odoo_configured,
    }


def require_odoo_config(config: RuntimeConfig | None = None) -> RuntimeConfig:
    runtime_config = RuntimeConfig.from_env() if config is None else config
    if not runtime_config.odoo_url:
        raise OdooConfigError("ODOO_URL is required for Odoo API calls")
    return runtime_config


def _register_odoo_components(server: FastMCP, config: RuntimeConfig) -> None:
    client = LazyOdooClient()
    register_generic_tools(server, client=client, settings=config)
    register_crm_tools(server, client, optional_features=config.crm_optional_features)
    register_resources(server, client=client, settings=config)
    register_prompts(server)


def _build_auth(config: RuntimeConfig) -> Any | None:
    if config.mcp_auth_mode == "none":
        return None
    if config.mcp_auth_mode == "static":
        from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

        if not config.mcp_static_token:
            raise OdooConfigError("MCP_STATIC_TOKEN is required when MCP_AUTH_MODE=static")
        return StaticTokenVerifier(
            tokens={
                config.mcp_static_token: {
                    "client_id": "odoo-mcp-static",
                    "scopes": ["odoo:read", "odoo:write", "odoo:admin"],
                }
            }
        )
    if config.mcp_auth_mode == "jwt":
        from fastmcp.server.auth.providers.jwt import JWTVerifier

        if not config.jwt_public_key and not config.jwt_jwks_uri:
            raise OdooConfigError(
                "JWT_PUBLIC_KEY or JWT_JWKS_URI is required when MCP_AUTH_MODE=jwt"
            )
        return JWTVerifier(
            public_key=config.jwt_public_key,
            jwks_uri=config.jwt_jwks_uri,
            issuer=config.jwt_issuer,
            audience=config.jwt_audience,
            required_scopes=list(config.jwt_required_scopes) or None,
        )
    raise OdooConfigError("MCP_AUTH_MODE must be one of: none, static, jwt")


def _config_items(config: RuntimeConfig) -> dict[str, JsonValue]:
    return {
        "odoo_url": config.odoo_url,
        "odoo_database": config.odoo_database,
        "odoo_api_key": config.odoo_api_key,
        "allowed_generic_methods": config.allowed_generic_methods,
        "crm_optional_features": list(config.crm_optional_features),
        "mcp_auth_mode": config.mcp_auth_mode,
        "mcp_static_token": config.mcp_static_token,
        "jwt_jwks_uri": config.jwt_jwks_uri,
        "jwt_issuer": config.jwt_issuer,
        "jwt_audience": config.jwt_audience,
        "jwt_public_key": config.jwt_public_key,
        "jwt_required_scopes": list(config.jwt_required_scopes),
        "http_host": config.http_host,
        "http_port": config.http_port,
        "http_path": config.http_path,
        "log_level": config.log_level,
    }


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _csv_tuple(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise OdooConfigError(f"MCP_HTTP_PORT must be an integer, got {value!r}") from exc
    if not 1 <= port <= 65535:
        raise OdooConfigError("MCP_HTTP_PORT must be between 1 and 65535")
    return port


def _normalize_path(value: str) -> str:
    stripped = value.strip() or DEFAULT_HTTP_PATH
    if stripped.startswith("/"):
        return stripped
    return f"/{stripped}"
