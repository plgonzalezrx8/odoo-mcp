"""Command-line entry points for the Odoo MCP runtime."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from odoo_mcp.exceptions import OdooMCPError
from odoo_mcp.server import RuntimeConfig, build_server, healthcheck_payload, inspect_config


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect-config":
            _print_json(inspect_config())
            return 0
        if args.command == "healthcheck":
            _print_json(healthcheck_payload())
            return 0
        if args.command == "http":
            return _run_http(args)
        if args.command == "stdio":
            return _run_stdio()

        parser.print_help(sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except OdooMCPError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="odoo-mcp",
        description="Run the Docker-first FastMCP server for Odoo JSON-2.",
    )
    subparsers = parser.add_subparsers(dest="command")

    stdio_parser = subparsers.add_parser("stdio", help="Run the MCP server over stdio.")
    stdio_parser.set_defaults(command="stdio")

    http_parser = subparsers.add_parser("http", help="Run the MCP server over HTTP.")
    http_parser.add_argument("--host", default=None, help="Bind host. Defaults to MCP_HTTP_HOST.")
    http_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bind port. Defaults to MCP_HTTP_PORT.",
    )
    http_parser.add_argument(
        "--path",
        default=None,
        help="MCP endpoint path. Defaults to MCP_HTTP_PATH.",
    )
    http_parser.add_argument(
        "--log-level",
        default=None,
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help="Uvicorn log level. Defaults to MCP_LOG_LEVEL.",
    )
    http_parser.add_argument(
        "--stateless-http",
        action="store_true",
        help="Run FastMCP HTTP transport in stateless mode.",
    )
    http_parser.set_defaults(command="http")

    inspect_parser = subparsers.add_parser(
        "inspect-config",
        help="Print sanitized runtime configuration as JSON.",
    )
    inspect_parser.set_defaults(command="inspect-config")

    health_parser = subparsers.add_parser(
        "healthcheck",
        help="Print local process readiness as JSON without contacting Odoo.",
    )
    health_parser.set_defaults(command="healthcheck")

    parser.set_defaults(command="stdio")
    return parser


def _run_stdio() -> int:
    server = build_server()
    server.run("stdio", show_banner=False)
    return 0


def _run_http(args: argparse.Namespace) -> int:
    config = RuntimeConfig.from_env()
    server = build_server(config)
    server.run(
        "http",
        host=args.host or config.http_host,
        port=args.port or config.http_port,
        path=args.path or config.http_path,
        log_level=args.log_level or config.log_level,
        show_banner=False,
        stateless_http=args.stateless_http,
    )
    return 0


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))
