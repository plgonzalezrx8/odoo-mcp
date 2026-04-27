"""Odoo MCP resource registration helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from odoo_mcp.tools.generic import (
    GenericOdooClient,
    _ensure_model_allowed,
    _ensure_read_allowed,
    _maybe_await,
    _normalize_limit,
    _require_model,
    _resolve_client,
    _resolve_safety,
)
from odoo_mcp.types import JsonObject, OdooDomain


class SupportsResourceRegistration(Protocol):
    def resource(
        self,
        uri: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


def register_resources(
    mcp: SupportsResourceRegistration,
    *,
    client: GenericOdooClient | None = None,
    settings: object | None = None,
    safety: object | None = None,
) -> None:
    """Register Odoo MCP resources on a FastMCP-compatible server."""

    @mcp.resource(
        "odoo://server/info",
        name="Odoo Server Info",
        description="Connection and version metadata for the configured Odoo server.",
    )
    async def server_info() -> JsonObject:
        active_client = _resolve_client(client, settings)
        info: JsonObject = {}
        if hasattr(active_client, "server_info"):
            info = await _maybe_await(active_client.server_info())
        return {
            "url": _setting_text(settings, ("odoo_url", "url", "base_url")),
            "database": _setting_text(settings, ("database", "odoo_database", "db")),
            "read_only": bool(_setting_value(settings, ("read_only", "mcp_read_only"), False)),
            "default_limit": _normalize_limit(None, settings),
            "odoo": info,
        }

    @mcp.resource(
        "odoo://user/context",
        name="Odoo User Context",
        description="Current Odoo user identity and effective context.",
    )
    async def user_context() -> JsonObject:
        active_client = _resolve_client(client, settings)
        user: JsonObject = dict(await _maybe_await(active_client.current_user(None)))
        context = user.pop("context", {})
        if not isinstance(context, dict):
            context = {}
        return cast(JsonObject, {"user": user, "context": context})

    @mcp.resource(
        "odoo://model/{model}/fields",
        name="Odoo Model Fields",
        description="Field metadata for an Odoo model.",
    )
    async def model_fields(model: str) -> JsonObject:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        safe_model = _require_model(model)
        _ensure_model_allowed(active_safety, safe_model)
        _ensure_read_allowed(active_safety, safe_model, None)
        fields: dict[str, JsonObject] = await _maybe_await(
            active_client.model_fields(safe_model, None, None)
        )
        return cast(JsonObject, {"model": safe_model, "fields": fields})

    @mcp.resource(
        "odoo://crm/pipeline/summary",
        name="CRM Pipeline Summary",
        description="Aggregated CRM opportunity counts and expected revenue by stage.",
    )
    async def crm_pipeline_summary() -> JsonObject:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        _ensure_model_allowed(active_safety, "crm.lead")
        _ensure_read_allowed(
            active_safety,
            "crm.lead",
            ["stage_id", "expected_revenue", "probability"],
        )
        _ensure_model_allowed(active_safety, "crm.stage")
        _ensure_read_allowed(active_safety, "crm.stage", ["name", "sequence"])

        stage_rows: list[JsonObject] = await _maybe_await(
            active_client.search_read(
                "crm.stage",
                [],
                ["name", "sequence"],
                200,
                0,
                "sequence asc",
                None,
            )
        )
        stage_names: dict[int, str] = {}
        for stage in stage_rows:
            stage_id = stage.get("id")
            stage_name = stage.get("name")
            if isinstance(stage_id, int) and not isinstance(stage_id, bool) and stage_name:
                stage_names[stage_id] = str(stage_name)

        lead_domain: OdooDomain = [("type", "=", "opportunity"), ("active", "=", True)]
        lead_rows: list[JsonObject] = await _maybe_await(
            active_client.search_read(
                "crm.lead",
                lead_domain,
                ["stage_id", "expected_revenue", "probability"],
                _normalize_limit(None, settings, default=200),
                0,
                None,
                None,
            )
        )
        return _summarize_pipeline(lead_rows, stage_names)


def _summarize_pipeline(rows: list[JsonObject], stage_names: dict[int, str]) -> JsonObject:
    buckets: dict[int | None, dict[str, Any]] = {}
    order: list[int | None] = []

    for row in rows:
        stage_id, stage_name = _stage_identity(row.get("stage_id"), stage_names)
        if stage_id not in buckets:
            order.append(stage_id)
            buckets[stage_id] = {
                "id": stage_id,
                "name": stage_name,
                "count": 0,
                "expected_revenue": 0.0,
                "_probability_total": 0.0,
            }
        bucket = buckets[stage_id]
        bucket["count"] += 1
        bucket["expected_revenue"] += _as_float(row.get("expected_revenue"))
        bucket["_probability_total"] += _as_float(row.get("probability"))

    stages: list[JsonObject] = []
    for stage_id in order:
        bucket = buckets[stage_id]
        count = int(bucket["count"])
        stages.append(
            {
                "id": bucket["id"],
                "name": bucket["name"],
                "count": count,
                "expected_revenue": bucket["expected_revenue"],
                "avg_probability": bucket["_probability_total"] / count if count else 0.0,
            }
        )

    return cast(
        JsonObject,
        {
            "model": "crm.lead",
            "total_count": len(rows),
            "total_expected_revenue": sum(_as_float(row.get("expected_revenue")) for row in rows),
            "stages": stages,
        },
    )


def _stage_identity(value: object, stage_names: dict[int, str]) -> tuple[int | None, str]:
    if isinstance(value, list | tuple) and value:
        stage_id = int(value[0])
        stage_name = str(value[1]) if len(value) > 1 and value[1] else stage_names.get(stage_id)
        return stage_id, stage_name or f"Stage {stage_id}"
    if isinstance(value, int) and not isinstance(value, bool):
        return value, stage_names.get(value, f"Stage {value}")
    return None, "Unassigned"


def _as_float(value: object) -> float:
    if value is None or value is False:
        return 0.0
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        return float(value) if value else 0.0
    return 0.0


def _setting_value(settings: object | None, names: tuple[str, ...], fallback: object) -> object:
    if settings is None:
        return fallback
    for name in names:
        value = getattr(settings, name, None)
        if value is not None:
            return value
    return fallback


def _setting_text(settings: object | None, names: tuple[str, ...]) -> str | None:
    value = _setting_value(settings, names, None)
    return str(value) if value is not None else None
