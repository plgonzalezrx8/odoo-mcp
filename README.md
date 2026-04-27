# odoo-mcp

Docker-first FastMCP server for Odoo 19 JSON-2 integrations.

`odoo-mcp` exposes Odoo as an MCP server over both HTTP and stdio. It uses the
Odoo 19 external JSON-2 API only:

```text
POST /json/2/<model>/<method>
Authorization: bearer <ODOO_API_KEY>
X-Odoo-Database: <optional database>
```

Legacy XML-RPC and JSON-RPC are intentionally out of scope.

## Status

This is an early implementation with a strong v1 foundation:

- FastMCP `3.2.4`
- Docker Compose first
- HTTP and stdio transports
- lazy Odoo credential loading so MCP discovery works before secrets are present
- guarded write operations with `confirm=True`
- generic Odoo tools
- comprehensive CRM tool pack
- resources and prompts for safe Odoo work
- pytest, ruff, mypy, and GitHub Actions CI

## Quick Start With Docker

Copy the environment template and edit the Odoo values:

```bash
cp .env.example .env
```

Required for real Odoo calls:

```bash
ODOO_URL=https://your-odoo-host.example.com
ODOO_API_KEY=your-odoo-api-key
ODOO_DATABASE=your-database-if-needed
```

Start the HTTP server:

```bash
docker compose up --build
```

The default MCP endpoint is:

```text
http://localhost:8000/mcp
```

Check local process readiness:

```bash
docker compose exec odoo-mcp uv run --no-sync odoo-mcp healthcheck
```

## Local Development

Install dependencies:

```bash
uv sync
```

Run the full gate:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Run HTTP locally:

```bash
uv run odoo-mcp http --host 0.0.0.0 --port 8000 --path /mcp
```

Run stdio locally:

```bash
uv run odoo-mcp stdio
```

Inspect sanitized config:

```bash
uv run odoo-mcp inspect-config
```

## MCP Client Config

Stdio example:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "uv",
      "args": ["run", "odoo-mcp", "stdio"],
      "env": {
        "ODOO_URL": "https://your-odoo-host.example.com",
        "ODOO_API_KEY": "your-odoo-api-key",
        "ODOO_DATABASE": "your-database-if-needed"
      }
    }
  }
}
```

HTTP clients should connect to `/mcp`. If the server is exposed beyond a trusted
network, set `MCP_AUTH_MODE=static` or `MCP_AUTH_MODE=jwt`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `ODOO_URL` | Base URL for Odoo 19 JSON-2 calls. |
| `ODOO_API_KEY` | Odoo API key sent as `Authorization: bearer ...`. |
| `ODOO_DATABASE` | Optional Odoo database header. |
| `ODOO_TIMEOUT_SECONDS` | HTTP timeout for Odoo calls. Defaults to `30`. |
| `ODOO_ALLOWED_GENERIC_METHODS` | Comma-separated allowlist for otherwise blocked generic methods. |
| `ODOO_CRM_OPTIONAL_FEATURES` | Comma-separated optional CRM features to expose. |
| `MCP_AUTH_MODE` | `none`, `static`, or `jwt`. Defaults to `none`. |
| `MCP_STATIC_TOKEN` | Bearer token for `MCP_AUTH_MODE=static`. |
| `JWT_JWKS_URI` | JWKS URL for `MCP_AUTH_MODE=jwt`. |
| `JWT_PUBLIC_KEY` | Public key alternative for JWT verification. |
| `JWT_ISSUER` | Optional expected JWT issuer. |
| `JWT_AUDIENCE` | Optional expected JWT audience. |
| `JWT_REQUIRED_SCOPES` | Optional comma-separated JWT scopes. |
| `MCP_HTTP_HOST` | HTTP bind host. Defaults to `0.0.0.0`. |
| `MCP_HTTP_PORT` | HTTP bind port. Defaults to `8000`. |
| `MCP_HTTP_PATH` | MCP endpoint path. Defaults to `/mcp`. |
| `MCP_LOG_LEVEL` | HTTP server log level. Defaults to `info`. |

## Tool Catalog

Generic Odoo tools:

- `odoo_search_read`
- `odoo_read`
- `odoo_create`
- `odoo_write`
- `odoo_unlink`
- `odoo_action`
- `odoo_call_method`
- `odoo_current_user`
- `odoo_model_fields`
- `odoo_list_models`

CRM tools:

- leads and opportunities: `crm_list_leads`, `crm_get_lead`, `crm_create_lead`,
  `crm_update_lead`, `crm_assign_lead`
- pipeline: `crm_list_pipeline_stages`, `crm_move_lead_to_stage`,
  `crm_pipeline_report`
- won/lost lifecycle: `crm_mark_won`, `crm_mark_lost`, `crm_restore_lead`,
  `crm_list_lost_reasons`
- conversion and merge: `crm_convert_lead_to_opportunity`,
  `crm_merge_opportunities`
- activities: `crm_schedule_activity`, `crm_mark_activity_done`,
  `crm_list_activities`, `crm_list_activity_types`, `crm_activity_report`
- teams and scoring: `crm_list_teams`, `crm_update_lead_score`
- optional features: `crm_enrich_lead`, `crm_list_scoring_rules`,
  `crm_recurring_revenue_report`

Optional CRM tools are registered only when their feature key is listed in
`ODOO_CRM_OPTIONAL_FEATURES`.

## Resources And Prompts

Resources:

- `odoo://server/info`
- `odoo://user/context`
- `odoo://model/{model}/fields`
- `odoo://crm/pipeline/summary`

Prompts:

- `odoo_safe_operation`
- `odoo_crm_pipeline_review`
- `odoo_record_change_plan`

## Safety Model

Odoo remains the final authorization layer through its access rights and record
rules. The MCP server adds local guardrails:

- mutating Odoo client calls require `confirm=True`
- generic dangerous methods such as `call_kw` and `execute_kw` are blocked unless
  explicitly allowlisted
- HTTP MCP auth is separate from the server-side Odoo API key
- `inspect-config` redacts secrets
- Odoo API errors redact configured secret values

Use `MCP_AUTH_MODE=static` for simple private HTTP deployments:

```bash
MCP_AUTH_MODE=static
MCP_STATIC_TOKEN=change-me
```

Use `MCP_AUTH_MODE=jwt` with `JWT_JWKS_URI` or `JWT_PUBLIC_KEY` for production
identity-provider-backed deployments.

## Extending

Add module packs under `src/odoo_mcp/tools/` and register them from
`src/odoo_mcp/server.py`. Prefer typed, curated tools for business workflows and
leave `odoo_call_method` as the explicit escape hatch.

When adding new Odoo workflows:

1. Write tests first with mocked Odoo JSON-2 behavior.
2. Prefer single-call Odoo methods like `search_read` because each JSON-2 call is
   its own transaction.
3. Require `confirm=True` for writes, actions, posting, validation, archive, and
   delete operations.
4. Add focused README entries for new tools and optional feature flags.
