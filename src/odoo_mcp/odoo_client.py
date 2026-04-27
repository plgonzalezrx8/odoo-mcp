"""Async client for Odoo 19 JSON-2 endpoints."""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote

import httpx

from odoo_mcp.config import OdooSettings, load_settings, redact_credentials
from odoo_mcp.exceptions import OdooAPIError
from odoo_mcp.safety import assert_method_allowed
from odoo_mcp.types import JsonObject, JsonValue


class OdooClient:
    """Small async transport wrapper for Odoo model method calls."""

    def __init__(
        self,
        settings: OdooSettings,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._http_client = http_client or httpx.AsyncClient(timeout=settings.timeout_seconds)
        self._owns_http_client = http_client is None

    async def __aenter__(self) -> OdooClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def call(
        self,
        model: str,
        method: str,
        *,
        ids: list[int] | None = None,
        context: JsonObject | None = None,
        confirm: bool = False,
        **named_args: Any,
    ) -> JsonValue:
        """Call ``POST /json/2/{model}/{method}`` with named JSON body arguments."""

        assert_method_allowed(
            method,
            confirm=confirm,
            allowed_generic_methods=self._settings.allowed_generic_methods,
        )

        body = self._build_body(ids=ids, context=context, named_args=named_args)
        url = self._url_for(model, method)
        headers = self._headers()

        try:
            response = await self._http_client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise OdooAPIError(f"Unable to reach Odoo: {exc}") from exc

        if response.status_code >= 400:
            raise self._api_error_from_response(response)

        return self._json_from_response(response)

    def _url_for(self, model: str, method: str) -> str:
        model_segment = quote(model, safe="")
        method_segment = quote(method, safe="")
        return f"{self._settings.base_url}/json/2/{model_segment}/{method_segment}"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._settings.database:
            headers["X-Odoo-Database"] = self._settings.database
        return headers

    def _build_body(
        self,
        *,
        ids: list[int] | None,
        context: JsonObject | None,
        named_args: dict[str, Any],
    ) -> JsonObject:
        body = dict(named_args)
        if ids is not None:
            body["ids"] = ids
        if context is not None:
            body["context"] = context
        return body

    def _json_from_response(self, response: httpx.Response) -> JsonValue:
        if not response.content:
            return None
        try:
            data = response.json()
        except ValueError as exc:
            raise OdooAPIError(
                f"Odoo returned invalid JSON with status {response.status_code}.",
                status_code=response.status_code,
            ) from exc
        return _json_value(data)

    def _api_error_from_response(self, response: httpx.Response) -> OdooAPIError:
        message = self._error_message(response)
        return OdooAPIError(message, status_code=response.status_code)

    def _error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text

        detail = _extract_error_detail(payload)
        redacted = redact_credentials(detail, secrets=(self._settings.api_key,))
        return f"Odoo API error {response.status_code}: {redacted}"

    async def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str] | None,
        limit: int,
        offset: int,
        order: str | None,
        context: JsonObject | None = None,
    ) -> list[JsonObject]:
        result = await self.call(
            model,
            "search_read",
            domain=domain,
            fields=fields,
            limit=limit,
            offset=offset,
            order=order,
            context=context,
        )
        return _json_rows(result)

    async def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
        context: JsonObject | None = None,
    ) -> list[JsonObject]:
        result = await self.call(model, "read", ids=ids, fields=fields, context=context)
        return _json_rows(result)

    async def create(
        self,
        model: str,
        values: JsonObject,
        context: JsonObject | None = None,
        *,
        confirm: bool = False,
    ) -> int | JsonValue:
        return await self.call(model, "create", values=values, context=context, confirm=confirm)

    async def write(
        self,
        model: str,
        ids: list[int],
        values: JsonObject,
        context: JsonObject | None = None,
        *,
        confirm: bool = False,
    ) -> bool:
        return bool(
            await self.call(
                model,
                "write",
                ids=ids,
                values=values,
                context=context,
                confirm=confirm,
            )
        )

    async def unlink(
        self,
        model: str,
        ids: list[int],
        context: JsonObject | None = None,
        *,
        confirm: bool = False,
    ) -> bool:
        return bool(await self.call(model, "unlink", ids=ids, context=context, confirm=confirm))

    async def call_method(
        self,
        model: str,
        method: str,
        *,
        args: list[JsonValue] | None = None,
        kwargs: JsonObject | None = None,
        context: JsonObject | None = None,
        confirm: bool = False,
    ) -> JsonValue:
        body: dict[str, Any] = dict(kwargs or {})
        if args is not None:
            body["args"] = args
        return await self.call(model, method, context=context, confirm=confirm, **body)

    async def current_user(self, context: JsonObject | None = None) -> JsonObject:
        result = await self.call("res.users", "context_get", context=context)
        return cast(JsonObject, result if isinstance(result, dict) else {"context": result})

    async def model_fields(
        self,
        model: str,
        attributes: list[str] | None = None,
        context: JsonObject | None = None,
    ) -> dict[str, JsonObject]:
        result = await self.call(model, "fields_get", attributes=attributes, context=context)
        if not isinstance(result, dict):
            return {}
        return {str(name): value for name, value in result.items() if isinstance(value, dict)}

    async def list_models(
        self,
        *,
        search: str | None = None,
        limit: int = 200,
        context: JsonObject | None = None,
    ) -> list[JsonObject]:
        domain: list[Any] = []
        if search:
            domain = ["|", ("model", "ilike", search), ("name", "ilike", search)]
        return await self.search_read(
            "ir.model",
            domain,
            ["model", "name", "state"],
            limit,
            0,
            "model asc",
            context,
        )

    async def server_info(self) -> JsonObject:
        return {
            "base_url": self._settings.base_url,
            "database": self._settings.database,
            "api": "json-2",
        }


class LazyOdooClient:
    """Resolve Odoo settings at tool-call time so MCP discovery needs no secrets."""

    async def call(self, model: str, method: str, **kwargs: Any) -> JsonValue:
        async with OdooClient(load_settings()) as client:
            return await client.call(model, method, **kwargs)

    async def search_read(
        self,
        model: str,
        domain: list[Any],
        fields: list[str] | None,
        limit: int,
        offset: int,
        order: str | None,
        context: JsonObject | None = None,
    ) -> list[JsonObject]:
        async with OdooClient(load_settings()) as client:
            return await client.search_read(model, domain, fields, limit, offset, order, context)

    async def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
        context: JsonObject | None = None,
    ) -> list[JsonObject]:
        async with OdooClient(load_settings()) as client:
            return await client.read(model, ids, fields, context)

    async def create(
        self,
        model: str,
        values: JsonObject,
        context: JsonObject | None = None,
        *,
        confirm: bool = False,
    ) -> int:
        async with OdooClient(load_settings()) as client:
            result = await client.create(model, values, context, confirm=confirm)
            return int(result) if isinstance(result, int) and not isinstance(result, bool) else 0

    async def write(
        self,
        model: str,
        ids: list[int],
        values: JsonObject,
        context: JsonObject | None = None,
        *,
        confirm: bool = False,
    ) -> bool:
        async with OdooClient(load_settings()) as client:
            return await client.write(model, ids, values, context, confirm=confirm)

    async def unlink(
        self,
        model: str,
        ids: list[int],
        context: JsonObject | None = None,
        *,
        confirm: bool = False,
    ) -> bool:
        async with OdooClient(load_settings()) as client:
            return await client.unlink(model, ids, context, confirm=confirm)

    async def call_method(
        self,
        model: str,
        method: str,
        *,
        args: list[JsonValue] | None = None,
        kwargs: JsonObject | None = None,
        context: JsonObject | None = None,
        confirm: bool = False,
    ) -> JsonValue:
        async with OdooClient(load_settings()) as client:
            return await client.call_method(
                model,
                method,
                args=args,
                kwargs=kwargs,
                context=context,
                confirm=confirm,
            )

    async def current_user(self, context: JsonObject | None = None) -> JsonObject:
        async with OdooClient(load_settings()) as client:
            return await client.current_user(context)

    async def model_fields(
        self,
        model: str,
        attributes: list[str] | None = None,
        context: JsonObject | None = None,
    ) -> dict[str, JsonObject]:
        async with OdooClient(load_settings()) as client:
            return await client.model_fields(model, attributes, context)

    async def list_models(
        self,
        *,
        search: str | None = None,
        limit: int = 200,
        context: JsonObject | None = None,
    ) -> list[JsonObject]:
        async with OdooClient(load_settings()) as client:
            return await client.list_models(search=search, limit=limit, context=context)

    async def server_info(self) -> JsonObject:
        settings = load_settings()
        return {
            "base_url": settings.base_url,
            "database": settings.database,
            "api": "json-2",
        }


def _extract_error_detail(payload: Any) -> JsonValue:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("name") or error.get("code")
            if message is not None:
                return _json_value(message)
            return _json_value(error)
        message = payload.get("message")
        if message is not None:
            return _json_value(message)
        return _json_value(payload)
    return _json_value(payload)


def _json_value(value: Any) -> JsonValue:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _json_rows(value: JsonValue) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]
