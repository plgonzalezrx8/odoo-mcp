from __future__ import annotations

import json

import httpx
import pytest

from odoo_mcp.config import OdooSettings
from odoo_mcp.exceptions import OdooAPIError, OdooSafetyError
from odoo_mcp.odoo_client import OdooClient


@pytest.mark.asyncio
async def test_call_posts_json_2_request_with_auth_database_and_named_args() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=[{"id": 1, "name": "Acme"}])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OdooClient(
            OdooSettings(
                base_url="https://example.odoo.com",
                api_key="super-secret-token",
                database="prod",
            ),
            http_client=http_client,
        )

        result = await client.call(
            "res.partner",
            "search_read",
            domain=[["is_company", "=", True]],
            fields=["name"],
            ids=[1],
            context={"lang": "en_US"},
        )

    assert result == [{"id": 1, "name": "Acme"}]
    assert captured_request is not None
    assert captured_request.method == "POST"
    assert str(captured_request.url) == "https://example.odoo.com/json/2/res.partner/search_read"
    assert captured_request.headers["Authorization"] == "Bearer super-secret-token"
    assert captured_request.headers["X-Odoo-Database"] == "prod"
    assert json.loads(captured_request.content) == {
        "domain": [["is_company", "=", True]],
        "fields": ["name"],
        "ids": [1],
        "context": {"lang": "en_US"},
    }


@pytest.mark.asyncio
async def test_call_omits_database_header_when_not_configured() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OdooClient(
            OdooSettings(base_url="https://example.odoo.com", api_key="token"),
            http_client=http_client,
        )

        await client.call("res.partner", "search_count", domain=[])

    assert captured_request is not None
    assert "X-Odoo-Database" not in captured_request.headers


@pytest.mark.asyncio
async def test_call_maps_odoo_error_response_and_redacts_credentials() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "message": "Access denied for super-secret-token",
                    "data": {"debug": "Authorization: Bearer super-secret-token"},
                }
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OdooClient(
            OdooSettings(base_url="https://example.odoo.com", api_key="super-secret-token"),
            http_client=http_client,
        )

        with pytest.raises(OdooAPIError) as exc_info:
            await client.call("res.partner", "search_read")

    assert exc_info.value.status_code == 403
    assert "Access denied" in str(exc_info.value)
    assert "super-secret-token" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_call_maps_transport_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OdooClient(
            OdooSettings(base_url="https://example.odoo.com", api_key="token"),
            http_client=http_client,
        )

        with pytest.raises(OdooAPIError) as exc_info:
            await client.call("res.partner", "search_read")

    assert "Unable to reach Odoo" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mutating_client_calls_require_confirmation() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"id": 10}))
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OdooClient(
            OdooSettings(base_url="https://example.odoo.com", api_key="token"),
            http_client=http_client,
        )

        with pytest.raises(OdooSafetyError):
            await client.call("res.partner", "create", name="Acme")


@pytest.mark.asyncio
async def test_confirmed_mutating_client_calls_are_sent() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json=True)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = OdooClient(
            OdooSettings(base_url="https://example.odoo.com", api_key="token"),
            http_client=http_client,
        )

        result = await client.call(
            "res.partner",
            "write",
            ids=[1],
            values={"name": "New"},
            confirm=True,
        )

    assert result is True
    assert captured_request is not None
    assert json.loads(captured_request.content) == {"ids": [1], "values": {"name": "New"}}
