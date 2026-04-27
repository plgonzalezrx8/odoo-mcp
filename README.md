# odoo-mcp

Docker-first FastMCP server for Odoo 19 JSON-2 integrations.

The runtime exposes one shared server factory used by both stdio and HTTP
transports. Odoo-specific tools can register against that factory from
`odoo_mcp.tools.register_tools(server, config)` or a compatible registry module.

## Quick Start

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your Odoo endpoint and credentials.

3. Start the HTTP server:

   ```bash
   docker compose up --build
   ```

4. Inspect local readiness:

   ```bash
   docker compose exec odoo-mcp uv run --no-sync odoo-mcp healthcheck
   ```

The default MCP endpoint is `http://localhost:8000/mcp`.

## Runtime Commands

Run over stdio for MCP clients that launch the server process directly:

```bash
odoo-mcp stdio
```

Run over HTTP:

```bash
odoo-mcp http --host 0.0.0.0 --port 8000 --path /mcp
```

Inspect sanitized configuration without exposing secrets:

```bash
odoo-mcp inspect-config
```

Check local process readiness without contacting Odoo:

```bash
odoo-mcp healthcheck
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `ODOO_URL` | Base URL for Odoo JSON-2 calls. Required by Odoo API tools. |
| `ODOO_DATABASE` | Optional Odoo database name. |
| `ODOO_USERNAME` | Optional Odoo username. |
| `ODOO_PASSWORD` | Optional Odoo password. Redacted by `inspect-config`. |
| `ODOO_API_KEY` | Optional Odoo API key. Redacted by `inspect-config`. |
| `JWT_SECRET` | Optional secret for future HTTP auth middleware. Redacted by `inspect-config`. |
| `MCP_HTTP_HOST` | HTTP bind host. Defaults to `0.0.0.0`. |
| `MCP_HTTP_PORT` | HTTP bind port. Defaults to `8000`. |
| `MCP_HTTP_PATH` | HTTP endpoint path. Defaults to `/mcp`. |
| `MCP_LOG_LEVEL` | Uvicorn log level. Defaults to `info`. |

## Development

Install and run tests with `uv`:

```bash
uv sync
uv run pytest
```

Static checks used by CI:

```bash
uv run ruff check .
uv run mypy
```

Docker is the target deployment path, but local Docker is not required for unit
tests. The Docker healthcheck uses `odoo-mcp healthcheck`, which validates the
server process wiring without making external network calls.

## Integration Points

The shared factory is `odoo_mcp.server.build_server()`. It always registers a
local `healthcheck` tool, then attempts to import tool registration from:

- `odoo_mcp.tools.register_tools`
- `odoo_mcp.tools.registry.register_tools`
- `odoo_mcp.tools.odoo.register_tools`

Compatible functions may accept either `(server)` or `(server, config)`. This is
intended to let the Odoo client, schema, and tool workers land independently
without changing the runtime entry points.
