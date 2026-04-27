from __future__ import annotations

import pytest

from odoo_mcp.resources import register_resources


class FakeMCP:
    def __init__(self) -> None:
        self.resources: dict[str, object] = {}

    def resource(self, uri: str, *, name: str | None = None, description: str | None = None):
        def decorator(func):
            self.resources[uri] = func
            func.resource_name = name
            func.description = description
            return func

        return decorator


class FakeSettings:
    odoo_url = "https://odoo.example.test"
    database = "demo"
    default_limit = 80
    read_only = True


class FakeSafety:
    def __init__(self) -> None:
        self.models: list[str] = []

    def ensure_model_allowed(self, model: str) -> None:
        self.models.append(model)

    def ensure_read_allowed(self, model: str, fields: list[str] | None = None) -> None:
        self.models.append(model)


class FakeClient:
    async def server_info(self):
        return {"version": "19.0", "server_serie": "19.0"}

    async def current_user(self, context=None):
        return {"id": 2, "name": "Demo", "context": {"lang": "en_US", "tz": "UTC"}}

    async def model_fields(self, model, attributes=None, context=None):
        return {"name": {"type": "char", "string": "Name"}}

    async def search_read(self, model, domain, fields, limit, offset, order, context=None):
        if model == "crm.stage":
            return [{"id": 1, "name": "New"}, {"id": 2, "name": "Won"}]
        return [
            {"stage_id": [1, "New"], "expected_revenue": 100.0, "probability": 25.0},
            {"stage_id": [2, "Won"], "expected_revenue": 300.0, "probability": 100.0},
            {"stage_id": False, "expected_revenue": 50.0, "probability": 10.0},
        ]


def test_registers_expected_resources() -> None:
    mcp = FakeMCP()

    register_resources(mcp, client=FakeClient(), settings=FakeSettings(), safety=FakeSafety())

    assert set(mcp.resources) == {
        "odoo://server/info",
        "odoo://user/context",
        "odoo://model/{model}/fields",
        "odoo://crm/pipeline/summary",
    }


@pytest.mark.asyncio
async def test_server_and_user_resources() -> None:
    mcp = FakeMCP()
    register_resources(mcp, client=FakeClient(), settings=FakeSettings(), safety=FakeSafety())

    assert await mcp.resources["odoo://server/info"]() == {
        "url": "https://odoo.example.test",
        "database": "demo",
        "read_only": True,
        "default_limit": 80,
        "odoo": {"version": "19.0", "server_serie": "19.0"},
    }
    assert await mcp.resources["odoo://user/context"]() == {
        "user": {"id": 2, "name": "Demo"},
        "context": {"lang": "en_US", "tz": "UTC"},
    }


@pytest.mark.asyncio
async def test_model_fields_resource_checks_safety() -> None:
    mcp = FakeMCP()
    safety = FakeSafety()
    register_resources(mcp, client=FakeClient(), settings=FakeSettings(), safety=safety)

    assert await mcp.resources["odoo://model/{model}/fields"]("res.partner") == {
        "model": "res.partner",
        "fields": {"name": {"type": "char", "string": "Name"}},
    }
    assert safety.models == ["res.partner", "res.partner"]


@pytest.mark.asyncio
async def test_crm_pipeline_summary_groups_open_leads_by_stage() -> None:
    mcp = FakeMCP()
    register_resources(mcp, client=FakeClient(), settings=FakeSettings(), safety=FakeSafety())

    result = await mcp.resources["odoo://crm/pipeline/summary"]()

    assert result == {
        "model": "crm.lead",
        "total_count": 3,
        "total_expected_revenue": 450.0,
        "stages": [
            {
                "id": 1,
                "name": "New",
                "count": 1,
                "expected_revenue": 100.0,
                "avg_probability": 25.0,
            },
            {
                "id": 2,
                "name": "Won",
                "count": 1,
                "expected_revenue": 300.0,
                "avg_probability": 100.0,
            },
            {
                "id": None,
                "name": "Unassigned",
                "count": 1,
                "expected_revenue": 50.0,
                "avg_probability": 10.0,
            },
        ],
    }
