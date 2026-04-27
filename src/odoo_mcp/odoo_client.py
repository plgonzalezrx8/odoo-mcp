"""Async client for Odoo 19 JSON-2 endpoints."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from odoo_mcp.config import OdooSettings, redact_credentials
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
