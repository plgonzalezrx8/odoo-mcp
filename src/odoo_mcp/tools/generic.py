"""Generic Odoo tool registration helpers."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol, TypeVar, cast, overload

from odoo_mcp.exceptions import OdooConfigError
from odoo_mcp.types import JsonObject, JsonValue, OdooDomain


class SupportsToolRegistration(Protocol):
    def tool(
        self, *, name: str, description: str | None = None
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


class GenericOdooClient(Protocol):
    async def search_read(
        self,
        model: str,
        domain: OdooDomain,
        fields: list[str] | None,
        limit: int,
        offset: int,
        order: str | None,
        context: JsonObject | None = None,
    ) -> list[JsonObject]: ...

    async def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
        context: JsonObject | None = None,
    ) -> list[JsonObject]: ...

    async def create(
        self,
        model: str,
        values: JsonObject,
        context: JsonObject | None = None,
        *,
        confirm: bool = False,
    ) -> int: ...

    async def write(
        self,
        model: str,
        ids: list[int],
        values: JsonObject,
        context: JsonObject | None = None,
        *,
        confirm: bool = False,
    ) -> bool: ...

    async def unlink(
        self,
        model: str,
        ids: list[int],
        context: JsonObject | None = None,
        *,
        confirm: bool = False,
    ) -> bool: ...

    async def current_user(self, context: JsonObject | None = None) -> JsonObject: ...

    async def model_fields(
        self,
        model: str,
        attributes: list[str] | None = None,
        context: JsonObject | None = None,
    ) -> dict[str, JsonObject]: ...


T = TypeVar("T")


def register_generic_tools(
    mcp: SupportsToolRegistration,
    *,
    client: GenericOdooClient | None = None,
    settings: object | None = None,
    safety: object | None = None,
) -> None:
    """Register generic Odoo MCP tools on a FastMCP-compatible server."""

    @mcp.tool(
        name="odoo_search_read",
        description="Search Odoo records and return selected fields using Odoo domains.",
    )
    async def odoo_search_read(
        model: str,
        domain: OdooDomain | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
        context: JsonObject | None = None,
    ) -> list[JsonObject]:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        safe_model = _require_model(model)
        safe_fields = _normalize_fields(fields)
        _ensure_model_allowed(active_safety, safe_model)
        _ensure_read_allowed(active_safety, safe_model, safe_fields)
        return await _maybe_await(
            active_client.search_read(
                safe_model,
                _normalize_domain(domain),
                safe_fields,
                _normalize_limit(limit, settings),
                _normalize_offset(offset),
                order,
                context,
            )
        )

    @mcp.tool(name="odoo_read", description="Read Odoo records by id.")
    async def odoo_read(
        model: str,
        ids: int | list[int],
        fields: list[str] | None = None,
        context: JsonObject | None = None,
    ) -> list[JsonObject]:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        safe_model = _require_model(model)
        safe_ids = _normalize_ids(ids)
        safe_fields = _normalize_fields(fields)
        _ensure_model_allowed(active_safety, safe_model)
        _ensure_read_allowed(active_safety, safe_model, safe_fields)
        return await _maybe_await(active_client.read(safe_model, safe_ids, safe_fields, context))

    @mcp.tool(name="odoo_create", description="Create an Odoo record after safety checks.")
    async def odoo_create(
        model: str,
        values: JsonObject,
        context: JsonObject | None = None,
        confirm: bool = False,
    ) -> int | JsonValue:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        safe_model = _require_model(model)
        safe_values = _normalize_values(values)
        if not confirm:
            from odoo_mcp.safety import assert_write_allowed

            assert_write_allowed(confirm=confirm, operation="create")
        _ensure_model_allowed(active_safety, safe_model)
        _ensure_write_allowed(active_safety, safe_model, safe_values)
        return await _maybe_await(
            active_client.create(safe_model, safe_values, context, confirm=confirm)
        )

    @mcp.tool(name="odoo_write", description="Update Odoo records after safety checks.")
    async def odoo_write(
        model: str,
        ids: int | list[int],
        values: JsonObject,
        context: JsonObject | None = None,
        confirm: bool = False,
    ) -> bool:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        safe_model = _require_model(model)
        safe_ids = _normalize_ids(ids)
        safe_values = _normalize_values(values)
        if not confirm:
            from odoo_mcp.safety import assert_write_allowed

            assert_write_allowed(confirm=confirm, operation="write")
        _ensure_model_allowed(active_safety, safe_model)
        _ensure_write_allowed(active_safety, safe_model, safe_values)
        return bool(
            await _maybe_await(
                active_client.write(safe_model, safe_ids, safe_values, context, confirm=confirm)
            )
        )

    @mcp.tool(name="odoo_unlink", description="Delete Odoo records after safety checks.")
    async def odoo_unlink(
        model: str,
        ids: int | list[int],
        context: JsonObject | None = None,
        confirm: bool = False,
    ) -> bool:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        safe_model = _require_model(model)
        safe_ids = _normalize_ids(ids)
        if not confirm:
            from odoo_mcp.safety import assert_write_allowed

            assert_write_allowed(confirm=confirm, operation="unlink")
        _ensure_model_allowed(active_safety, safe_model)
        _ensure_unlink_allowed(active_safety, safe_model, safe_ids)
        return bool(
            await _maybe_await(active_client.unlink(safe_model, safe_ids, context, confirm=confirm))
        )

    @mcp.tool(name="odoo_action", description="Execute a named Odoo action.")
    async def odoo_action(
        action: str,
        model: str | None = None,
        record_ids: list[int] | None = None,
        context: JsonObject | None = None,
    ) -> JsonValue:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        safe_action = _require_non_empty(action, "action")
        safe_model = _require_model(model) if model is not None else None
        safe_ids = _normalize_ids(record_ids) if record_ids is not None else None
        _ensure_action_allowed(active_safety, safe_action, safe_model)
        if hasattr(active_client, "action"):
            return await _maybe_await(
                active_client.action(
                    safe_action, model=safe_model, record_ids=safe_ids, context=context
                )
            )
        return await _call_client_method(
            active_client,
            "ir.actions.actions",
            "_for_xml_id",
            args=[safe_action],
            kwargs={"context": context} if context else {},
            context=context,
        )

    @mcp.tool(name="odoo_call_method", description="Call an allowed Odoo model method.")
    async def odoo_call_method(
        model: str,
        method: str,
        args: list[JsonValue] | None = None,
        kwargs: JsonObject | None = None,
        context: JsonObject | None = None,
        confirm: bool = False,
    ) -> JsonValue:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        safe_model = _require_model(model)
        safe_method = _require_non_empty(method, "method")
        _ensure_model_allowed(active_safety, safe_model)
        _ensure_method_allowed(active_safety, safe_model, safe_method)
        return await _call_client_method(
            active_client,
            safe_model,
            safe_method,
            args=args or [],
            kwargs=kwargs or {},
            context=context,
            confirm=confirm,
        )

    @mcp.tool(name="odoo_current_user", description="Return the current Odoo user.")
    async def odoo_current_user(context: JsonObject | None = None) -> JsonObject:
        active_client = _resolve_client(client, settings)
        return await _maybe_await(active_client.current_user(context))

    @mcp.tool(name="odoo_model_fields", description="Return field metadata for an Odoo model.")
    async def odoo_model_fields(
        model: str,
        attributes: list[str] | None = None,
        context: JsonObject | None = None,
    ) -> dict[str, JsonObject]:
        active_client = _resolve_client(client, settings)
        active_safety = _resolve_safety(safety, settings)
        safe_model = _require_model(model)
        _ensure_model_allowed(active_safety, safe_model)
        _ensure_read_allowed(active_safety, safe_model, None)
        return await _maybe_await(active_client.model_fields(safe_model, attributes, context))

    @mcp.tool(name="odoo_list_models", description="List available Odoo models.")
    async def odoo_list_models(
        search: str | None = None,
        limit: int | None = 200,
        context: JsonObject | None = None,
    ) -> list[JsonObject]:
        active_client = _resolve_client(client, settings)
        safe_limit = _normalize_limit(limit, settings, default=200)
        if hasattr(active_client, "list_models"):
            return await _maybe_await(
                active_client.list_models(search=search, limit=safe_limit, context=context)
            )

        domain: OdooDomain = []
        if search:
            domain = ["|", ("model", "ilike", search), ("name", "ilike", search)]
        return await _maybe_await(
            active_client.search_read(
                "ir.model",
                domain,
                ["model", "name", "state"],
                safe_limit,
                0,
                "model asc",
                context,
            )
        )


async def _call_client_method(
    client: object,
    model: str,
    method: str,
    *,
    args: list[JsonValue] | None,
    kwargs: JsonObject | None,
    context: JsonObject | None,
    confirm: bool = False,
) -> JsonValue:
    if hasattr(client, "call_method"):
        return await _maybe_await(
            client.call_method(
                model,
                method,
                args=args or [],
                kwargs=kwargs or {},
                context=context,
                confirm=confirm,
            )
        )
    if hasattr(client, "call"):
        body = dict(kwargs or {})
        if args:
            body["args"] = args
        return await _maybe_await(
            client.call(model, method, context=context, confirm=confirm, **body)
        )
    if hasattr(client, "execute_kw"):
        return await _maybe_await(
            client.execute_kw(model, method, args or [], kwargs or {}, context)
        )
    msg = "Configured Odoo client does not expose call_method, call, or execute_kw."
    raise OdooConfigError(msg)


def _resolve_client[T](client: T | None, settings: object | None) -> T:
    if client is not None:
        return client

    for module_name in ("odoo_mcp.client", "odoo_mcp.odoo", "odoo_mcp.clients"):
        try:
            module = __import__(module_name, fromlist=["_"])
        except ImportError:
            continue
        for factory_name in ("get_odoo_client", "get_client", "create_client"):
            factory = getattr(module, factory_name, None)
            if factory is None:
                continue
            try:
                resolved = factory(settings) if settings is not None else factory()
            except TypeError:
                resolved = factory()
            return cast(T, resolved)
        client_cls = getattr(module, "OdooClient", None)
        if client_cls is not None:
            try:
                return (
                    cast(T, client_cls(settings)) if settings is not None else cast(T, client_cls())
                )
            except TypeError:
                return cast(T, client_cls())

    raise OdooConfigError("No Odoo client was provided and no client factory could be resolved.")


def _resolve_safety(safety: object | None, settings: object | None) -> object | None:
    if safety is not None:
        return safety

    for module_name in ("odoo_mcp.safety", "odoo_mcp.security"):
        try:
            module = __import__(module_name, fromlist=["_"])
        except ImportError:
            continue
        for factory_name in ("get_safety", "create_safety", "SafetyPolicy"):
            factory = getattr(module, factory_name, None)
            if factory is None:
                continue
            try:
                return cast(object, factory(settings) if settings is not None else factory())
            except TypeError:
                return cast(object, factory())
    return None


@overload
async def _maybe_await[T](value: Awaitable[T]) -> T: ...


@overload
async def _maybe_await[T](value: T) -> T: ...


async def _maybe_await[T](value: T | Awaitable[T]) -> T:
    if inspect.isawaitable(value):
        return await cast(Awaitable[T], value)
    return value


def _call_safety(safety: object | None, names: Sequence[str], *args: object) -> None:
    if safety is None:
        return
    for name in names:
        method = getattr(safety, name, None)
        if method is not None:
            method(*args)
            return


def _ensure_model_allowed(safety: object | None, model: str) -> None:
    _call_safety(safety, ("ensure_model_allowed", "check_model_allowed", "validate_model"), model)


def _ensure_read_allowed(safety: object | None, model: str, fields: list[str] | None) -> None:
    _call_safety(
        safety,
        ("ensure_read_allowed", "check_read_allowed", "validate_read"),
        model,
        fields,
    )


def _ensure_write_allowed(safety: object | None, model: str, values: JsonObject) -> None:
    _call_safety(
        safety,
        ("ensure_write_allowed", "check_write_allowed", "validate_write"),
        model,
        values,
    )


def _ensure_unlink_allowed(safety: object | None, model: str, ids: list[int]) -> None:
    _call_safety(
        safety,
        ("ensure_unlink_allowed", "check_unlink_allowed", "validate_unlink"),
        model,
        ids,
    )


def _ensure_action_allowed(safety: object | None, action: str, model: str | None) -> None:
    _call_safety(
        safety,
        ("ensure_action_allowed", "check_action_allowed", "validate_action"),
        action,
        model,
    )


def _ensure_method_allowed(safety: object | None, model: str, method: str) -> None:
    _call_safety(
        safety,
        ("ensure_method_allowed", "check_method_allowed", "validate_method"),
        model,
        method,
    )


def _normalize_domain(domain: OdooDomain | None) -> OdooDomain:
    return list(domain or [])


def _normalize_fields(fields: list[str] | None) -> list[str] | None:
    if fields is None:
        return None
    return [_require_non_empty(field, "field") for field in fields]


def _normalize_ids(ids: int | Sequence[int]) -> list[int]:
    raw_ids = [ids] if isinstance(ids, int) else list(ids)
    if not raw_ids:
        raise ValueError("At least one record id is required.")
    normalized = [int(record_id) for record_id in raw_ids]
    if any(record_id <= 0 for record_id in normalized):
        raise ValueError("Record ids must be positive integers.")
    return normalized


def _normalize_values(values: Mapping[str, JsonValue]) -> JsonObject:
    if not values:
        raise ValueError("Values must include at least one field.")
    return dict(values)


def _normalize_limit(
    limit: int | None,
    settings: object | None,
    *,
    default: int | None = None,
) -> int:
    fallback = default or _setting_int(settings, ("default_limit", "odoo_default_limit"), 80)
    max_limit = _setting_int(settings, ("max_limit", "odoo_max_limit"), 500)
    normalized = fallback if limit is None else int(limit)
    if normalized < 1:
        raise ValueError("Limit must be greater than zero.")
    return min(normalized, max_limit)


def _normalize_offset(offset: int) -> int:
    normalized = int(offset)
    if normalized < 0:
        raise ValueError("Offset must be zero or greater.")
    return normalized


def _setting_int(settings: object | None, names: Sequence[str], fallback: int) -> int:
    if settings is None:
        return fallback
    for name in names:
        value = getattr(settings, name, None)
        if value is not None:
            return int(value)
    return fallback


def _require_model(model: str) -> str:
    value = _require_non_empty(model, "model")
    if "." not in value:
        raise ValueError("Odoo model names must use dotted technical names.")
    return value


def _require_non_empty(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} is required.")
    return normalized
