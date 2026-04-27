from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from odoo_mcp import cli
from odoo_mcp.server import RuntimeConfig, build_server, inspect_config


async def test_build_server_returns_named_fastmcp_with_health_tool() -> None:
    server = build_server(RuntimeConfig(odoo_url="https://odoo.example.com"))

    assert isinstance(server, FastMCP)
    assert server.name == "odoo-mcp"
    assert await server.get_tool("healthcheck") is not None


def test_inspect_config_redacts_sensitive_values(monkeypatch) -> None:
    monkeypatch.setenv("ODOO_URL", "https://odoo.example.com")
    monkeypatch.setenv("ODOO_DATABASE", "prod")
    monkeypatch.setenv("ODOO_USERNAME", "admin@example.com")
    monkeypatch.setenv("ODOO_PASSWORD", "secret")
    monkeypatch.setenv("ODOO_API_KEY", "api-secret")
    monkeypatch.setenv("JWT_SECRET", "jwt-secret")

    payload = inspect_config()

    assert payload["odoo_url"] == "https://odoo.example.com"
    assert payload["odoo_database"] == "prod"
    assert payload["odoo_username"] == "admin@example.com"
    assert payload["odoo_password"] == "***"
    assert payload["odoo_api_key"] == "***"
    assert payload["jwt_secret"] == "***"


def test_inspect_config_command_prints_json(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ODOO_URL", "https://odoo.example.com")

    exit_code = cli.main(["inspect-config"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["odoo_url"] == "https://odoo.example.com"
    assert "odoo_password" not in payload


def test_healthcheck_command_reports_ready_without_network(capsys) -> None:
    exit_code = cli.main(["healthcheck"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["server"] == "odoo-mcp"


def test_stdio_command_runs_fastmcp_stdio(monkeypatch) -> None:
    calls: list[tuple[str | None, dict[str, Any]]] = []

    def fake_run(self: FastMCP, transport: str | None = None, **kwargs: Any) -> None:
        calls.append((transport, kwargs))

    monkeypatch.setattr(FastMCP, "run", fake_run)

    assert cli.main(["stdio"]) == 0
    assert calls == [("stdio", {"show_banner": False})]


def test_http_command_runs_fastmcp_http_with_runtime_options(monkeypatch) -> None:
    calls: list[tuple[str | None, dict[str, Any]]] = []

    def fake_run(self: FastMCP, transport: str | None = None, **kwargs: Any) -> None:
        calls.append((transport, kwargs))

    monkeypatch.setattr(FastMCP, "run", fake_run)

    assert (
        cli.main(
            [
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                "9000",
                "--path",
                "/mcp",
                "--log-level",
                "debug",
            ]
        )
        == 0
    )
    assert calls == [
        (
            "http",
            {
                "host": "127.0.0.1",
                "port": 9000,
                "path": "/mcp",
                "log_level": "debug",
                "show_banner": False,
                "stateless_http": False,
            },
        )
    ]
