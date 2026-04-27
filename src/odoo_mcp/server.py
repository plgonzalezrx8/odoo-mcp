"""Shared FastMCP server factory and runtime configuration."""

from __future__ import annotations

import inspect
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastmcp import FastMCP

from odoo_mcp import __version__
from odoo_mcp.exceptions import OdooConfigError
from odoo_mcp.types import JsonObject, JsonValue

SERVER_NAME = "odoo-mcp"
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8000
DEFAULT_HTTP_PATH = "/mcp"
DEFAULT_LOG_LEVEL = "info"

_REDACTED = "***"
_SENSITIVE_KEYS = {"odoo_password", "odoo_api_key", "jwt_secret"}


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Runtime settings consumed by the server factory and CLI."""

    odoo_url: str | None = None
    odoo_database: str | None = None
    odoo_username: str | None = None
    odoo_password: str | None = None
    odoo_api_key: str | None = None
    jwt_secret: str | None = None
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
            odoo_username=_empty_to_none(env.get("ODOO_USERNAME")),
            odoo_password=_empty_to_none(env.get("ODOO_PASSWORD")),
            odoo_api_key=_empty_to_none(env.get("ODOO_API_KEY")),
            jwt_secret=_empty_to_none(env.get("JWT_SECRET")),
            http_host=env.get("MCP_HTTP_HOST", DEFAULT_HTTP_HOST),
            http_port=_parse_port(env.get("MCP_HTTP_PORT", str(DEFAULT_HTTP_PORT))),
            http_path=_normalize_path(env.get("MCP_HTTP_PATH", DEFAULT_HTTP_PATH)),
            log_level=env.get("MCP_LOG_LEVEL", DEFAULT_LOG_LEVEL),
        )

    @property
    def odoo_configured(self) -> bool:
        return bool(self.odoo_url)

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
    )

    @server.tool(name="healthcheck", description="Return local server readiness metadata.")
    def healthcheck_tool() -> dict[str, Any]:
        return healthcheck_payload(runtime_config)

    _register_external_tools(server, runtime_config)
    return server


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


def _register_external_tools(server: FastMCP, config: RuntimeConfig) -> None:
    """Import tool registration from worker-owned modules when they exist."""

    for import_path in (
        "odoo_mcp.tools",
        "odoo_mcp.tools.registry",
        "odoo_mcp.tools.odoo",
    ):
        try:
            module_name, _, attribute = import_path.partition(":")
            module = __import__(module_name, fromlist=[attribute or "register_tools"])
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise

        register = getattr(module, "register_tools", None)
        if callable(register):
            _call_register_tools(register, server, config)


def _call_register_tools(
    register: Callable[..., Any],
    server: FastMCP,
    config: RuntimeConfig,
) -> None:
    parameters = inspect.signature(register).parameters
    if len(parameters) >= 2:
        register(server, config)
    else:
        register(server)


def _config_items(config: RuntimeConfig) -> dict[str, JsonValue]:
    return {
        "odoo_url": config.odoo_url,
        "odoo_database": config.odoo_database,
        "odoo_username": config.odoo_username,
        "odoo_password": config.odoo_password,
        "odoo_api_key": config.odoo_api_key,
        "jwt_secret": config.jwt_secret,
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
